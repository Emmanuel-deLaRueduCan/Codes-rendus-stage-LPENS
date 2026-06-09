import time

import numpy as np

import os
from os.path import exists

import threading

from dataclasses import dataclass

from ids_peak import ids_peak
from ids_peak_ipl import ids_peak_ipl
from ids_peak_icv.pipeline import DefaultPipeline
from ids_peak_common import PixelFormat

TARGET_PIXEL_FORMAT = PixelFormat.BGRA_8

@dataclass
class RecordingStatistics:
    frames_encoded: int
    frames_stream_dropped: int
    frames_video_dropped: int
    frames_lost_stream: int
    duration: int

    def fps(self):
        return self.frames_encoded / self.duration

class Camera:

    def __init__(self, device_manager, interface):

        self.device_manager = device_manager
        self._interface = interface
        self._device = None
        self._datastream = None
        self._acquisition_running = False
        self.start_recording = False
        self.target_fps = 0
        self.max_fps = 0
        self.target_gain = 1
        self.max_gain = 1
        self.acquisition_time = 5
        self._node_map = None
        self.killed = False

        interface._camera = self

        self._get_device()

        self._setup_device_and_datastream()

        self._image_pipeline = DefaultPipeline()
        self._image_pipeline.output_pixel_format = TARGET_PIXEL_FORMAT

    def __del__(self):
        if self._device is None or self._acquisition_running is False:
            return
        try:
            self._node_map.FindNode("AcquisitionStop").Execute()

            # Stop and flush the `DataStream`.
            # `KillWait` will cancel pending `WaitForFinishedBuffer` calls.
            # NOTE: One call to `KillWait` will cancel one pending `WaitForFinishedBuffer`.
            #       For more information, refer to the documentation of `KillWait`.
            self._datastream.KillWait()
            self._datastream.StopAcquisition(ids_peak.AcquisitionStopMode_Default)
            # Discard all buffers from the acquisition engine.
            # They remain in the announced buffer pool.
            self._datastream.Flush(ids_peak.DataStreamFlushMode_DiscardAll)

            self._acquisition_running = False

            # Unlock parameters
            self._node_map.FindNode("TLParamsLocked").SetValue(0)

        except Exception as e:
            print(f"Exception (stop acquisition): {str(e)}")

        # final check
        if self._datastream is not None:
            try:
                for buffer in self._datastream.AnnouncedBuffers():
                    self._datastream.RevokeBuffer(buffer)
            except Exception as e:
                print(f"Exception (close): {str(e)}")

    ## define which device will be used and set its principal characteristics
    def _get_device(self):

        selected_device = None
        li_devices=[]

        self.device_manager.Update()
        li_devices = self.device_manager.Devices()

        # no device found
        if len(li_devices) == 0:
            print("No device found. Exiting Program.")
            return
        # only one device found
        elif len(li_devices) == 1:
            selected_device = 0
        # several devices found, let the user make their choice
        else:
            for i, device in enumerate(li_devices):
                print(
                    f"{str(i)}:  {device.ModelName()} ("
                    f"{device.ParentInterface().DisplayName()} ; "
                    f"{device.ParentInterface().ParentSystem().DisplayName()} v." 
                    f"{device.ParentInterface().ParentSystem().Version()})")
            while True:
                try:
                    selected_device = int(input("Select device to open: "))
                    if selected_device < len(li_devices):
                        break
                    else:
                        print("Invalid ID.")
                except ValueError:
                    print("Please enter a correct id.")
                    continue

        self._device = li_devices[selected_device].OpenDevice(ids_peak.DeviceAccessType_Control)
        
        # loading of the camera's node map, a set of parameters such as exposure, gain or firmware info.

        self._node_map = self._device.RemoteDevice().NodeMaps()[0]
        self._node_map.FindNode("UserSetSelector").SetCurrentEntry("Default")
        self._node_map.FindNode("UserSetLoad").Execute()
        self._node_map.FindNode("UserSetLoad").WaitUntilDone()


        self.max_fps = self._node_map.FindNode("AcquisitionFrameRate").Maximum()
        self.target_fps = self.max_fps

        self.max_gain = self._node_map.FindNode("Gain").Maximum()

    ## create a queue where the data will be transferred and all the buffers necessary for its recovery 
    ## with the right size (neither too small nor too big)
    def _setup_device_and_datastream(self):

        self._datastream = self._device.DataStreams()[0].OpenDataStream()

        payload_size = self._node_map.FindNode("PayloadSize").Value()
        for _ in range(self._datastream.NumBuffersAnnouncedMinRequired() * 5):
            buffer = self._datastream.AllocAndAnnounceBuffer(payload_size)
            self._datastream.QueueBuffer(buffer)

        print("Allocated buffers, finished opening device")
    
    ## check if it's possible to begin the acquisition, if it is lock the parameters et start the acquisition for the camera and the program
    def start_acquisition(self):

        if self._device is None:
            return False
        if self._acquisition_running is True:
            return True

        try:
            self._node_map.FindNode("TLParamsLocked").SetValue(1)

            self._datastream.StartAcquisition()
            self._node_map.FindNode("AcquisitionStart").Execute()
            self._node_map.FindNode("AcquisitionStart").WaitUntilDone()

            self._acquisition_running = True
            return True
        
        except Exception as e:
            print(f"Exception (start acquisition): {str(e)}")
            return False

    def _valid_name(self, path: str, ext = ""):
        num = 0

        def build_string():
            return f"{path}_{num}{ext}"

        while exists(build_string()):
            num += 1
        return build_string()

    ## manage all the recording
    def record(self, timer: int):
        cwd = os.getcwd()

        video = ids_peak_ipl.VideoWriter()
        
        dropped_before = 0
        lost_before = 0

        video_np=[]
        video_proprieties={}

        try:
            # Create a new file where the video will be saved in.
            video.Open(self._valid_name(cwd + "/" + "video", ".avi"))

            video.Container().SetFramerate(self.target_fps)

            print("Recording with: \n"
                  f"  Framerate: {self._node_map.FindNode("AcquisitionFrameRate").Value():.2f}\n"
                  f"  Gain: {self._node_map.FindNode("Gain").Value():.2f}")
            
            data_stream_node_map = self._datastream.NodeMaps()[0]
            dropped_before = data_stream_node_map.FindNode("StreamDroppedFrameCount").Value()
            lost_before = data_stream_node_map.FindNode("StreamLostFrameCount").Value()

        except Exception as e:
            self._interface.warning(str(e))
            raise

        print("Recording...")
        # Set target time
        limit = timer + time.time()

        while (limit - time.time()) > 0 and not self.killed:
            try:
                #get the current image
                buffer = self._datastream.WaitForFinishedBuffer(500)
                image_view = buffer.ToImageView()
                converted_image = self._image_pipeline.process(image_view)
                data = converted_image.to_numpy_array().flatten()

                #extraction of important data
                video_proprieties['value']=converted_image.pixel_format.value
                video_proprieties['width']=converted_image.width
                video_proprieties['height']=converted_image.height
                video_proprieties['size']=np.shape(data)

                #.avi format
                video.Append(ids_peak_ipl.Image.CreateFromSizeAndPythonBuffer(converted_image.pixel_format.value, data, converted_image.width, converted_image.height))
                
                #.npy format
                video_np.append(np.array([data[4*k*converted_image.width:4*(k+1)*converted_image.width:4] for k in range(converted_image.height)]))

                # Give buffer back into the queue to used it again
                self._datastream.QueueBuffer(buffer)

            except Exception as e:
                print(f"Warning: Exception caught: {str(e)}")

        if self.killed:
            return 

        #calculation of the statitics
        dropped_stream_frames = data_stream_node_map.FindNode("StreamDroppedFrameCount").Value() - dropped_before
        lost_stream_frames = data_stream_node_map.FindNode("StreamLostFrameCount").Value() - lost_before

        stats = RecordingStatistics(
            frames_encoded=video.NumFramesEncoded(),
            frames_video_dropped=video.NumFramesDropped(),
            frames_stream_dropped=dropped_stream_frames,
            frames_lost_stream=lost_stream_frames,
            duration=timer)
        video.Container().SetFramerate(stats.fps())

        video.WaitUntilFrameDone(10000)
        video.Close()

        #backup of the video under the .npy format
        np.save(self._valid_name(cwd + "/" + "video", ".npy"),np.array(video_np))

        self._interface.done_recording(stats)

    ## define the thread which will stay activate as background
    def acquisition_thread(self):
        while not self.killed:
            try:
                if self.start_recording:
                    self.record(self.acquisition_time)
                    self.start_recording = False

            except Exception as e:
                self._interface.warning(str(e))
                self.start_recording = False
                self._interface.done_recording(RecordingStatistics(0, 0, 0, 0, 0))

class Interface:

    def __init__(self):
        self._camera = None
        self._acquisition_thread = None

    def warning(self, message: str):
        print("Warning:", message)

    def done_recording(self, stats: RecordingStatistics):
        if stats.frames_encoded != 0:
            self._camera.recording_running = False
            print("Recording done!\n"
                  "Statistics:\n"
                  f"  Total Frames recorded: {stats.frames_encoded}\n"
                  f"  Frames dropped by video recorder: {stats.frames_video_dropped}\n"
                  f"  Frames dropped by image stream: {stats.frames_stream_dropped}\n"
                  f"  Frames lost by image stream: {stats.frames_lost_stream}\n"
                  f"  Frame rate: {stats.fps()}")

    # Common interface end

    def print_help(self):
        print("Commands:\n"
              "help: Display help text\n"
              "exit: Exit the program (alias quit)\n"
              "set_framerate: Set the target framerate\n"
              "set_gain: Set the gain\n"
              "set_acquisition_time: set the acquisition time\n"
              "start: Start the image acquisition record a video")

    def get_value(self, prompt_text: str, default: float):
        while True:
            string = input(prompt_text)
            if not string.strip():
                continue

            try:
                return float(string)
            except ValueError:
                print(f"Error: '{string}' is not convertible to a float!")

    def prompt(self):
        if self._camera is None:
            raise RuntimeError("Missing camera!")

        self.print_help()
        try:
            while True:
                command = input("> ").strip()
                if command in ("quit", "exit"):
                    break
                elif command == "help":
                    self.print_help()
                elif command == "set_framerate":
                    self._camera.target_fps = self.get_value(
                        f"Camera framerate (current: {self._camera.target_fps:.2f}): ",
                        self._camera.target_fps)
                elif command == "set_gain":
                    self._camera.target_gain = self.get_value(
                        f"Camera gain (current: {self._camera.target_gain:.2f}): ",
                        self._camera.target_gain)
                elif command == "set_acquisition_time":
                    self._camera.acquisition_time = self.get_value(
                        f"Camera acquisition time (current: {self._camera.acquisition_time:.2f}): ",
                        self._camera.acquisition_time)
                elif command == "start":
                    print("Will use the following settings for recording:\n"
                          f"Camera framerate: {self._camera.target_fps:.2f}\n"
                          f"Camera gain:      {self._camera.target_gain:.2f}\n"
                          f"Acquisition time: {self._camera.acquisition_time:.2f}")
                    self._camera.start_recording = True
                    while self._camera.start_recording:
                        time.sleep(0.01)
                else:
                     print(f"Command: {command} not found!")
        except KeyboardInterrupt:
            print("KeyboardInterrupt: Stopping...")
        finally:
            self._camera.killed = True
            if self._acquisition_thread is not None:
                self._acquisition_thread.join()

# Initialize library and create a device manager

ids_peak.Library.Initialize()
device_manager = ids_peak.DeviceManager.Instance()

camera_device = None
interface = None

try:

    interface=Interface()
    camera_device = Camera(device_manager, interface)

    if not camera_device.start_acquisition():
        print("Unable to start acquisition!")

    else:
        print("Acquisition started")

        thread = threading.Thread(target=camera_device.acquisition_thread)
        interface.acquisition_thread = thread
        thread.start()

        interface.prompt()

except Exception as e:

    print(f"Exception (main): {str(e)}")

finally:

    # Close camera and library after program ends
    if camera_device is not None:
        camera_device.__del__()
    ids_peak.Library.Close()
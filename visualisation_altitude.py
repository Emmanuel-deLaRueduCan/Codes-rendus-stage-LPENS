import numpy as np
import cupy as cp
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider

import magtrack

#Load the video and the calibration image
#don't forget to change the path if it's necessary
video_np = np.load("/home/manip/Desktop/codes/Rapport/Code/Good_video.npy")[:,270:370,540:640]
zlut= np.load("/home/manip/Desktop/codes/Rapport/Code/Good_calibr.npy")
current_img = video_np[0]

t_max, global_side_x, global_side_y= video_np.shape

# Choose the time and the part of the image 
def selection(t,x,y,side):
    if t>t_max or x+int(side/2)>global_side_x or x-int(side/2)<0 or y+int(side/2)>global_side_y or y-int(side/2)<0:
        print('Format error')
    else:
        return video_np[t][y-int(side/2):y+int(side/2),x-int(side/2):x+int(side/2)]

#Find the center of mass along the time with magtrack
x_com,y_com=magtrack.center_of_mass(cp.asarray(video_np.T.astype('float64')), background="median")
x_com_b, y_com_b = magtrack.auto_conv_sub_pixel(cp.asarray(video_np.T.astype('float64')), x_com, y_com)
x_com=cp.asnumpy(x_com)
y_com=cp.asnumpy(y_com)
x_com_b=cp.asnumpy(x_com_b)
y_com_b=cp.asnumpy(y_com_b)

#Calculate the radial profils
profiles = 1/255 * magtrack.radial_profile(video_np.T.astype('float64'), x_com_b, y_com_b)

# Calculate the z coordinate
z_fit = magtrack.lookup_z(255 * profiles[:23,:], zlut)

# Define initial parameters
#Normally global_side_x = global_side_y := global_side

global_side = global_side_x

init_t = 0
init_x = int(global_side_x/2)
init_y = int(global_side_y/2)
init_side = global_side
show_pointer = True
show_profile = False

# Create the figure and the line that we will manipulate
fig,ax = plt.subplots(1,3)

# adjust the main plot to make room for the sliders
fig.subplots_adjust(bottom=0.2)

# Make a slider to control the current image .
ax_t = fig.add_axes([0.2, 0.1, 0.65, 0.03])
t_slider = Slider(
    ax = ax_t,
    label = 'Time (frame)',
    valmin = 0,
    valmax = t_max,
    valinit = init_t,
)

# The function to be called anytime a slider's value changes
def update(val):

    current_img=selection(int(t_slider.val),init_x,init_y,init_side)

    plt.subplot(1,3,1)
    plt.cla()
    plt.imshow(current_img,cmap='gray',vmin=0,vmax=255)
    plt.title('Current image',fontsize=48)
    if show_pointer == True:
        plt.plot(y_com_b[int(t_slider.val)],x_com_b[int(t_slider.val)], 'gv', label='Better Center-of-Mass')
    # if show_profile == True:
    #     plt.plot(x_com_b[int(t_slider.val)] + np.arange(profiles.shape[0]), y_com_b[int(t_slider.val)] + profiles[:, int(t_slider.val)]*init_side/6, 'r', label='Profile')


    plt.subplot(1,3,2)
    plt.cla()
    plt.plot(profiles[:, int(t_slider.val)], 'r')
    plt.ylim(0, 1)
    plt.xlabel('Distance from center (pixel)',fontsize=32)
    plt.ylabel('Intensity',fontsize=32)
    plt.title('Current profile',fontsize=48)

    plt.subplot(1,3,3)
    plt.plot(z_fit, linestyle='--')
    plt.xlabel('Frame number',fontsize=32)
    plt.ylabel('Z (ua)',fontsize=32)
    plt.title('Z(t)',fontsize=48)

    fig.canvas.draw_idle()
    

# register the update function with each slider
t_slider.on_changed(update)

# Create a `matplotlib.widgets.Button` to reset the sliders to initial values.
resetax = fig.add_axes([0.02, 0.02, 0.1, 0.04])
button_reset = Button(resetax, 'Reset', hovercolor='0.975')

# Create a `matplotlib.widgets.Button` to increment time.
resetax = fig.add_axes([0.14, 0.02, 0.1, 0.04])
button_increment = Button(resetax, 'Increment (t)', hovercolor='0.975')

# Create a `matplotlib.widgets.Button` to show pointers
resetax = fig.add_axes([0.26, 0.02, 0.1, 0.04])
button_pointer = Button(resetax, 'Pointer ON/OFF', hovercolor='0.975')

# Create a `matplotlib.widgets.Button` to show profile
# resetax = fig.add_axes([0.38, 0.02, 0.1, 0.04])
# button_profile = Button(resetax, 'Profile ON/OFF', hovercolor='0.975')

def increment(event):
    t_slider.val = t_slider.val + 1
    update(None)

def pointer_OnOff(event):
    global show_pointer
    show_pointer = not(show_pointer)

# def profile_OnOff(event):
#     global show_profile
#     show_profile = not(show_profile)

def reset(event):
    t_slider.reset()

button_reset.on_clicked(reset)
button_increment.on_clicked(increment)
button_pointer.on_clicked(pointer_OnOff)
#button_profile.on_clicked(profile_OnOff)

plt.show()


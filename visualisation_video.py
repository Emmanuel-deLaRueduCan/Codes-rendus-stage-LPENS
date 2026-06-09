import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button, Slider

#Load the video
#change the path if it'snecessary
video_np = np.load("/home/manip/Desktop/codes/Rapport/Code/Good_video.npy")[:,:,400:1168]
current_img = video_np[0]

t_max, global_side_x, global_side_y= video_np.shape

# Choose the time and the part of the image 
def selection(t,x,y,side):
    if t>t_max or x+int(side/2)>global_side_x or x-int(side/2)<0 or y+int(side/2)>global_side_y or y-int(side/2)<0:
        print('Format error')
    else:
        return video_np[t][y-int(side/2):y+int(side/2),x-int(side/2):x+int(side/2)]

# Define initial parameters
#Normally global_side_x = global_side_y := global_side

global_side = min(global_side_x,global_side_y)

init_t = 0
init_x = int(global_side_x/2)
init_y = int(global_side_y/2)
init_side = global_side
show_pointer = True

# Create the figure and the line that we will manipulate
fig,ax = plt.subplots(1,1)

# adjust the main plot to make room for the sliders
fig.subplots_adjust(left=0.2, bottom=0.2)

# Make a slider to control the vertical position .
ax_y = fig.add_axes([0.05, 0.2, 0.0225, 0.63])
y_slider = Slider(
    ax = ax_y,
    label = 'Vertical\n (pixels)',
    valmin = 0,
    valmax = global_side_y,
    valinit = init_y,
    orientation = "vertical"
)

# Make a slider to control the horizontal position .
ax_x = fig.add_axes([0.1, 0.2, 0.0225, 0.63])
x_slider = Slider(
    ax=ax_x,
    label='Horizontal\n (pixels)',
    valmin=0,
    valmax=global_side_x,
    valinit=init_x,
    orientation = "vertical"
)

# Make a slider to control the current image .
ax_t = fig.add_axes([0.2, 0.1, 0.65, 0.03])
t_slider = Slider(
    ax = ax_t,
    label = 'Time (frame)',
    valmin = 0,
    valmax = t_max,
    valinit = init_t,
)
# Make a slider to control the size of the image.
ax_side = fig.add_axes([0.2, 0.05, 0.65, 0.03])
side_slider = Slider(
    ax = ax_side,
    label = 'Side (pixels)',
    valmin = 0,
    valmax = global_side,
    valinit = init_side,
)

# The function to be called anytime a slider's value changes
def update(val):

    current_img=selection(int(t_slider.val),int(x_slider.val),int(y_slider.val),int(side_slider.val))

    plt.subplot(1,1,1)
    plt.cla()
    plt.imshow(current_img,cmap='gray',vmin=0,vmax=255)

    fig.canvas.draw_idle()
    


# register the update function with each slider
t_slider.on_changed(update)
x_slider.on_changed(update)
y_slider.on_changed(update)
side_slider.on_changed(update)

# Create a `matplotlib.widgets.Button` to reset the sliders to initial values.
resetax = fig.add_axes([0.02, 0.02, 0.1, 0.04])
button_reset = Button(resetax, 'Reset', hovercolor='0.975')

# Create a `matplotlib.widgets.Button` to increment time.
resetax = fig.add_axes([0.02, 0.07, 0.1, 0.04])
button_increment = Button(resetax, 'Increment (t)', hovercolor='0.975')


def increment(event):
    t_slider.val = t_slider.val + 1
    update(None)

def pointer_OnOff(show_pointer):
    show_pointer = not(show_pointer)

def reset(event):
    t_slider.reset()
    x_slider.reset()
    y_slider.reset()
    side_slider.reset()

button_reset.on_clicked(reset)
button_increment.on_clicked(increment)

plt.show()


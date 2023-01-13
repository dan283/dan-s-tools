from tkinter import *
from tkinter import messagebox
import subprocess
from tkinter.colorchooser import askcolor
from tkinter import colorchooser
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from random import randint, choice, shuffle

# ---------------------------- PASSWORD GENERATOR ------------------------------- #

import os
from tkinter import filedialog as fd
FONT = 'e:/scripts/Minecraftia-Regular.ttf'
filenames = ""


def choose_color():
    # variable to store hexadecimal code of color
    color_code = colorchooser.askcolor(title="Choose color")
    print(color_code[0])
    return color_code[0]


text_color = choose_color


def convert_to_jpg():
    for filename in filenames:
        im = Image.open(filename)
        rgb_im = im.convert("RGB")
        file_name = os.path.basename(filename[:-4])
        file_path = os.path.dirname(filename)
        rgb_im.save(os.path.join(file_path, f"jpg_{file_name}.jpg"))

def resize():

    for filename in filenames:
        im = Image.open(filename)
        print(filename)
        im_resized = im.resize((512, 512))
        file_name = os.path.basename(filename[:-4])
        file_path = os.path.dirname(filename)
        print(file_name)
        print(file_path)
        im_resized.save(os.path.join(file_path, f"{file_name}_512.png"))


def select_files():
    global filenames
    filetypes = (
        ('image files', '*.png'),
        ('All files', '*.*')
    )

    filenames = fd.askopenfilenames(
        title='Open files',
        initialdir='/',
        filetypes=filetypes)

    # input_website.delete(0, END)
    # input_website.insert(0, filenames)
    for filename in filenames:
        file_name = os.path.basename(filename)
        listbox.insert('end', file_name)


def concatinate():

    image_list = []
    wide_image_width = []

    # Populating 2 lists, one of which is used to determine final image width, the other as images to concatinate
    for filename in filenames:
        file_name = os.path.basename(filename)
        file_path = os.path.dirname(filename)
        dir = os.listdir(file_path)
        im = Image.open(filename)
        width, height = im.size
        wide_image_width.append(width)
        image_list.append(filename)

    final_width = (sum(wide_image_width) + len(wide_image_width) * 30) - 30
    img = Image.new('RGBA', (final_width, height), color='black')
    img.save('pil_black.png')

    im = Image.open('pil_black.png')
    for i, filename in enumerate(filenames):
        images = Image.open(filename).convert("RGBA")
        im.paste(images, (width * (i) + 30 * i, 0), images)

    im.save(os.path.join(file_path, f"concatinated_{file_name}"))


def textify():
    text = input_password.get()
    text_list = list(text.split(","))


    # Storing width and height for placement purposes
    font_size = 100
    font = ImageFont.truetype("arial.ttf", font_size)

    for i, filename in enumerate(filenames):
        im = Image.open(filename)
        draw = ImageDraw.Draw(im)
        width, height = im.size
        text_anchor = ""
        text_position_height = 0
        text_length = font.getlength(text_list[i])


        if variable.get() == "bottom":
            text_anchor = "mb"
            text_position_height = height - (font_size+50)
            text_position_width = width / 2
        elif variable.get() == "top":
            text_anchor = "mt"
            text_position_height = 50
            text_position_width = width / 2
        elif variable.get() == "left":
            text_anchor = "lm"
            text_position_width = 0
            text_position_height = height / 2

        print(width)
        print(width/2)
        print(text_anchor)
        print(list(text.split(",")))
        file_name = os.path.basename(filename)
        file_path = os.path.dirname(filename)

        draw.text((
            text_position_width-text_length/2,
            text_position_height),
            text_list[i],
            (255, 255, 255),
            font=font,
            text_anchor="mm")

        im.save(os.path.join(file_path, f"text_{file_name}"))


def logofy():
    LOGO = 'exoLogoWhiteOnBlack_alpha_smallX.png' # exoLogoWhiteOnBlack_alpha_smallX.png, ooze_inc_logo.png, GREYSKULL_small.png, exoLogoWhiteOnBlack_alpha.png
    logoIm = Image.open(LOGO)
    logo_width, logo_height = logoIm.size

    factor = 1.075  # increase contrast


    global filenames

    for filename in filenames:
        im = Image.open(filename)
        width, height = im.size
        file_name = os.path.basename(filename)
        file_path = os.path.dirname(filename)

        # Comment out to keep image as is, else increases contrast just a touch
        enhancer = ImageEnhance.Contrast(im)
        im = enhancer.enhance(factor)

        print("Adding logo to %s..." % (filename))
        im.paste(logoIm, (30, 10), logoIm) #lower right - width - logo_width - 30, height - logo_height - 10
        im = im.convert("RGB")
        im.save(os.path.join(file_path, f"logo_{file_name}.jpg"), "JPEG")



# ---------------------------- UI SETUP ------------------------------- #
window = Tk()
window.title("Dan's Image Tools")
window.config( padx=10, pady=20, bg="#242A38")

# Dropdown Menu
variable = StringVar(window)
variable.set("bottom") # default value

w = OptionMenu(window, variable, "bottom", "top", "left" )
w.config(fg="#FFFFFF", bg="#4E586E", borderwidth=0, highlightthickness=1, font=("Helvetica", 12), highlightcolor="#737373", highlightbackground="#808080")
w.grid(column=2, row=3, pady=5, ipadx=15)

label_website = Label(text="Dan's Image Tools", bg="#242A38", font=('Minecraftia', 25), fg="#FFFFFF")
label_website.grid(column=0, row=0, columnspan=3, pady=5)

label_open = Label(text="Open File >>>", bg="#242A38", font=("Helvetica", 12, "bold"), fg="#FFFFFF")
label_open.grid(column=0, row=1, pady=5)

listbox = Listbox(window)
listbox.grid(column=0, row=2, columnspan=3, sticky="nsew")

input_password = Entry(width=34, bg="#FFFFFF")
input_password.grid(column=1, row=3, pady=5, padx=10)
input_password.insert(0, "ADD TEXT TO IMAGE")


# Buttons
button_logofy = Button(text="Logofy", fg="#FFFFFF", bg="#4E586E", command=logofy, font=("Helvetica", 12))
button_logofy.grid(column=0, row=4, pady=2, ipadx=30)

button_gen_pass = Button(text="Stripify", fg="#FFFFFF", bg="#4E586E", command=concatinate, font=("Helvetica", 12))
button_gen_pass.grid(column=1, row=4, pady=2, ipadx=30)

button_gen_pass = Button(text="Textify", fg="#FFFFFF", bg="#4E586E", command=textify, font=("Helvetica", 12))
button_gen_pass.grid(column=2, row=4, pady=2, ipadx=30)

button_gen_pass = Button(text="Open File", fg="#FFFFFF", bg="#4E586E", command=select_files, font=("Helvetica", 12))
button_gen_pass.grid(column=1, row=1, pady=4, ipadx=20)

button_gen_pass = Button(text="Convert to JPG", fg="#FFFFFF", bg="#4E586E", command=convert_to_jpg, font=("Helvetica", 12))
button_gen_pass.grid(column=2, row=1, pady=4, ipadx=5)

button_gen_pass = Button(text="Text color", fg="#FFFFFF", bg="#4E586E", command=choose_color, font=("Helvetica", 12))
button_gen_pass.grid(column=0, row=3, pady=4, ipadx=20)

button_gen_pass = Button(text="Resize to 512", fg="#FFFFFF", bg="#4E586E", command=resize, font=("Helvetica", 12))
button_gen_pass.grid(column=0, row=5, pady=4, ipadx=5)


window.mainloop()

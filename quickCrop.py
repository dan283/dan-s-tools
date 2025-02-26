import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os


class ImageCropper:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Cropper")

        self.image_list = []
        self.current_image_index = 0
        self.rect = None
        self.start_x = self.start_y = 0
        self.crop_coords = None
        self.auto_save = tk.BooleanVar()
        self.suffix = tk.StringVar()

        # UI Components
        self.canvas = tk.Canvas(root, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.btn_frame = tk.Frame(root)
        self.btn_frame.pack()

        self.load_btn = tk.Button(self.btn_frame, text="Load Images", command=self.load_images)
        self.load_btn.pack(side=tk.LEFT)

        self.prev_btn = tk.Button(self.btn_frame, text="Previous", command=self.prev_image)
        self.prev_btn.pack(side=tk.LEFT)

        self.next_btn = tk.Button(self.btn_frame, text="Next", command=self.next_image)
        self.next_btn.pack(side=tk.LEFT)

        self.save_btn = tk.Button(self.btn_frame, text="Save Crop", command=self.save_crop)
        self.save_btn.pack(side=tk.LEFT)

        self.suffix_entry = tk.Entry(self.btn_frame, textvariable=self.suffix, width=10)
        self.suffix_entry.pack(side=tk.LEFT)
        self.suffix_entry.insert(0, "_cropped")

        self.auto_save_check = tk.Checkbutton(self.btn_frame, text="Auto Save", variable=self.auto_save)
        self.auto_save_check.pack(side=tk.LEFT)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

    def load_images(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.bmp;*.gif")])
        if not file_paths:
            return
        self.image_list = list(file_paths)
        self.current_image_index = 0
        self.display_image()

    def display_image(self):
        if not self.image_list:
            return
        image_path = self.image_list[self.current_image_index]
        self.img = Image.open(image_path)
        self.tk_img = ImageTk.PhotoImage(self.img)
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_img)
        self.canvas.config(scrollregion=self.canvas.bbox(tk.ALL))
        self.crop_coords = None

    def prev_image(self):
        if self.current_image_index > 0:
            self.current_image_index -= 1
            self.display_image()

    def next_image(self):
        if self.current_image_index < len(self.image_list) - 1:
            self.current_image_index += 1
            self.display_image()

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="red")

    def on_drag(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        self.crop_coords = (self.start_x, self.start_y, event.x, event.y)

    def save_crop(self):
        if not self.crop_coords or not self.image_list:
            messagebox.showerror("Error", "No crop region selected or no image loaded!")
            return

        x1, y1, x2, y2 = self.crop_coords
        cropped = self.img.crop((x1, y1, x2, y2))

        if self.auto_save.get():
            image_path = self.image_list[self.current_image_index]
            dir_name, base_name = os.path.split(image_path)
            name, ext = os.path.splitext(base_name)
            save_path = os.path.join(dir_name, f"{name}{self.suffix.get()}{ext}")
            cropped.save(save_path)
            messagebox.showinfo("Success", f"Cropped image saved automatically as {save_path}")
        else:
            save_path = filedialog.asksaveasfilename(defaultextension=".png",
                                                     filetypes=[("PNG", "*.png"), ("JPG", "*.jpg")])
            if save_path:
                cropped.save(save_path)
                messagebox.showinfo("Success", "Cropped image saved successfully!")


if __name__ == "__main__":
    root = tk.Tk()
    app = ImageCropper(root)
    root.mainloop()

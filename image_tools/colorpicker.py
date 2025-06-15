import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os


class ColorPicker:
    def __init__(self, root):
        self.root = root
        self.root.title("Color Picker Tool")
        self.root.geometry("800x600")

        # Variables
        self.image = None
        self.photo = None
        self.canvas_width = 600
        self.canvas_height = 400
        self.current_rgb_01 = None

        # Create UI elements
        self.create_widgets()

    def create_widgets(self):
        # Frame for buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        # Load image button
        load_btn = tk.Button(button_frame, text="Load Image", command=self.load_image)
        load_btn.pack(side=tk.LEFT, padx=5)

        # Canvas for image display
        self.canvas = tk.Canvas(self.root, width=self.canvas_width, height=self.canvas_height,
                                bg='gray', cursor='crosshair')
        self.canvas.pack(pady=10)
        self.canvas.bind("<Button-1>", self.pick_color)

        # Frame for color info
        info_frame = tk.Frame(self.root)
        info_frame.pack(pady=10)

        # Labels for color information
        tk.Label(info_frame, text="RGB (0-255):").grid(row=0, column=0, sticky='w')
        self.rgb_255_label = tk.Label(info_frame, text="Click on image to pick color",
                                      font=('Courier', 10))
        self.rgb_255_label.grid(row=0, column=1, sticky='w', padx=10)

        tk.Label(info_frame, text="RGB (0-1):").grid(row=1, column=0, sticky='w')
        self.rgb_01_label = tk.Label(info_frame, text="", font=('Courier', 10))
        self.rgb_01_label.grid(row=1, column=1, sticky='w', padx=10)

        # Color preview
        tk.Label(info_frame, text="Color:").grid(row=2, column=0, sticky='w')
        self.color_preview = tk.Label(info_frame, text="      ", bg='white',
                                      relief='solid', borderwidth=1)
        self.color_preview.grid(row=2, column=1, sticky='w', padx=10, pady=5)

        # Copy button
        self.copy_btn = tk.Button(info_frame, text="Copy RGB (0-1)", command=self.copy_to_clipboard,
                                  state='disabled')
        self.copy_btn.grid(row=3, column=1, sticky='w', padx=10, pady=5)

        # Instructions
        instructions = tk.Label(self.root,
                                text="Instructions: Load an image, then click anywhere on it to get RGB values",
                                fg='gray')
        instructions.pack(pady=5)

    def load_image(self):
        file_path = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                ("All files", "*.*")
            ]
        )

        if file_path:
            try:
                # Load and store the original image
                self.image = Image.open(file_path)

                # Create a copy for display, maintaining aspect ratio
                display_image = self.image.copy()

                # Calculate scaling to fit canvas while maintaining aspect ratio
                img_width, img_height = display_image.size
                scale_x = self.canvas_width / img_width
                scale_y = self.canvas_height / img_height
                scale = min(scale_x, scale_y)

                new_width = int(img_width * scale)
                new_height = int(img_height * scale)

                display_image = display_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Convert to PhotoImage and display
                self.photo = ImageTk.PhotoImage(display_image)

                # Clear canvas and center the image
                self.canvas.delete("all")
                x_offset = (self.canvas_width - new_width) // 2
                y_offset = (self.canvas_height - new_height) // 2

                self.canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=self.photo)

                # Store scaling info for coordinate conversion
                self.scale = scale
                self.x_offset = x_offset
                self.y_offset = y_offset

                # Reset color info
                self.rgb_255_label.config(text="Click on image to pick color")
                self.rgb_01_label.config(text="")
                self.color_preview.config(bg='white')
                self.copy_btn.config(state='disabled')
                self.current_rgb_01 = None

            except Exception as e:
                messagebox.showerror("Error", f"Could not load image: {str(e)}")

    def pick_color(self, event):
        if self.image is None:
            messagebox.showwarning("Warning", "Please load an image first")
            return

        # Convert canvas coordinates to original image coordinates
        canvas_x = event.x
        canvas_y = event.y

        # Check if click is within the image bounds
        if (canvas_x < self.x_offset or canvas_x >= self.x_offset + self.photo.width() or
                canvas_y < self.y_offset or canvas_y >= self.y_offset + self.photo.height()):
            return

        # Convert to original image coordinates
        img_x = int((canvas_x - self.x_offset) / self.scale)
        img_y = int((canvas_y - self.y_offset) / self.scale)

        # Ensure coordinates are within image bounds
        img_x = max(0, min(img_x, self.image.width - 1))
        img_y = max(0, min(img_y, self.image.height - 1))

        try:
            # Get pixel color
            if self.image.mode == 'RGBA':
                r, g, b, a = self.image.getpixel((img_x, img_y))
            elif self.image.mode == 'RGB':
                r, g, b = self.image.getpixel((img_x, img_y))
            else:
                # Convert to RGB if it's in a different mode
                rgb_image = self.image.convert('RGB')
                r, g, b = rgb_image.getpixel((img_x, img_y))

            # Update labels with RGB values
            self.rgb_255_label.config(text=f"({r}, {g}, {b})")

            # Convert to 0-1 range and format to 3 decimal places
            r_01 = round(r / 255.0, 3)
            g_01 = round(g / 255.0, 3)
            b_01 = round(b / 255.0, 3)

            # Store current RGB (0-1) values
            self.current_rgb_01 = (r_01, g_01, b_01)

            self.rgb_01_label.config(text=f"({r_01:.3f}, {g_01:.3f}, {b_01:.3f})")

            # Update color preview
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            self.color_preview.config(bg=hex_color)

            # Enable copy button
            self.copy_btn.config(state='normal')

        except Exception as e:
            messagebox.showerror("Error", f"Could not pick color: {str(e)}")

    def copy_to_clipboard(self):
        if self.current_rgb_01 is None:
            return

        r, g, b = self.current_rgb_01
        # Format as (0.000, 0.000, 0.000)
        rgb_text = f"({r:.3f}, {g:.3f}, {b:.3f})"

        # Copy to clipboard
        self.root.clipboard_clear()
        self.root.clipboard_append(rgb_text)
        self.root.update()  # Update clipboard

        # Show confirmation
        messagebox.showinfo("Copied", f"RGB values copied to clipboard:\n{rgb_text}")


def main():
    root = tk.Tk()
    app = ColorPicker(root)
    root.mainloop()


if __name__ == "__main__":
    main()

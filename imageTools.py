import tkinter as tk
from tkinter import ttk, messagebox, filedialog, colorchooser
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from pathlib import Path


class ImageProcessingTool:
    def __init__(self, root):
        self.root = root
        self.setup_window()
        self.setup_variables()
        self.create_widgets()

        # File management
        self.selected_files = []
        self.logo_path = ""
        self.output_directory = ""
        self.text_color = (255, 255, 255)  # Default white

    def setup_window(self):
        self.root.title("Image Processing Suite")
        self.root.geometry("700x600")
        self.root.configure(bg='#2a2a2a')
        self.root.resizable(True, True)

    def setup_variables(self):
        self.text_position = tk.StringVar(value="bottom")
        self.logo_position = tk.StringVar(value="top-left")
        self.text_size = tk.IntVar(value=100)
        self.apply_to_all = tk.BooleanVar(value=False)

    def create_widgets(self):
        # Header
        header = tk.Frame(self.root, bg='#1a1a1a', height=60)
        header.pack(fill='x', pady=(0, 10))
        header.pack_propagate(False)

        tk.Label(header, text="🖼️ Image Processing Suite",
                 font=('Segoe UI', 16, 'bold'), fg='white', bg='#1a1a1a').pack(pady=15)

        # Main container
        main_frame = tk.Frame(self.root, bg='#2a2a2a')
        main_frame.pack(fill='both', expand=True, padx=20, pady=10)

        # File Management Section
        self.create_file_section(main_frame)

        # Settings Section
        self.create_settings_section(main_frame)

        # Actions Section
        self.create_actions_section(main_frame)

    def create_file_section(self, parent):
        # File management frame
        file_frame = tk.LabelFrame(parent, text="📁 Files", font=('Segoe UI', 12, 'bold'),
                                   bg='#2a2a2a', fg='white', bd=1, relief='solid')
        file_frame.pack(fill='x', pady=(0, 10))

        # Buttons row
        btn_frame = tk.Frame(file_frame, bg='#2a2a2a')
        btn_frame.pack(fill='x', padx=10, pady=10)

        tk.Button(btn_frame, text="📁 Select Images", command=self.select_files,
                  bg='#404040', fg='white', font=('Segoe UI', 9), relief='flat',
                  padx=15, pady=5).pack(side='left', padx=(0, 10))

        tk.Button(btn_frame, text="🏷️ Select Logo", command=self.select_logo,
                  bg='#505050', fg='white', font=('Segoe UI', 9), relief='flat',
                  padx=15, pady=5).pack(side='left', padx=(0, 10))

        tk.Button(btn_frame, text="📂 Output Folder", command=self.select_output_directory,
                  bg='#606060', fg='white', font=('Segoe UI', 9), relief='flat',
                  padx=15, pady=5).pack(side='left')

        # File list
        list_frame = tk.Frame(file_frame, bg='#2a2a2a')
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))

        self.file_listbox = tk.Listbox(list_frame, bg='#404040', fg='white',
                                       selectbackground='#606060', height=4,
                                       font=('Segoe UI', 9), relief='solid', bd=1)
        self.file_listbox.pack(side='left', fill='both', expand=True)

        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=self.file_listbox.yview)
        scrollbar.pack(side='right', fill='y')
        self.file_listbox.configure(yscrollcommand=scrollbar.set)

        # Status labels
        self.logo_status = tk.Label(file_frame, text="🏷️ No logo selected",
                                    bg='#2a2a2a', fg='#cccccc', font=('Segoe UI', 8))
        self.logo_status.pack(anchor='w', padx=10)

        self.output_status = tk.Label(file_frame, text="📂 Output: Same as input files",
                                      bg='#2a2a2a', fg='#cccccc', font=('Segoe UI', 8))
        self.output_status.pack(anchor='w', padx=10, pady=(0, 10))

    def create_settings_section(self, parent):
        # Settings notebook
        settings_frame = tk.LabelFrame(parent, text="⚙️ Settings", font=('Segoe UI', 12, 'bold'),
                                       bg='#2a2a2a', fg='white', bd=1, relief='solid')
        settings_frame.pack(fill='x', pady=(0, 10))

        notebook = ttk.Notebook(settings_frame)
        notebook.pack(fill='x', padx=10, pady=10)

        # Text settings tab
        text_tab = tk.Frame(notebook, bg='#2a2a2a')
        notebook.add(text_tab, text='📝 Text')

        # Text content
        tk.Label(text_tab, text="Text:", bg='#2a2a2a', fg='white',
                 font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', padx=10, pady=5)

        self.text_entry = tk.Entry(text_tab, bg='#404040', fg='white', font=('Segoe UI', 10),
                                   insertbackground='white', relief='solid', bd=1)
        self.text_entry.grid(row=0, column=1, sticky='ew', padx=(0, 10), pady=5)
        self.text_entry.insert(0, "Sample Text")
        text_tab.grid_columnconfigure(1, weight=1)

        # Font size
        tk.Label(text_tab, text="Size:", bg='#2a2a2a', fg='white',
                 font=('Segoe UI', 10)).grid(row=1, column=0, sticky='w', padx=10, pady=5)

        size_frame = tk.Frame(text_tab, bg='#2a2a2a')
        size_frame.grid(row=1, column=1, sticky='w', padx=(0, 10), pady=5)

        self.size_scale = tk.Scale(size_frame, from_=20, to=200, orient='horizontal',
                                   variable=self.text_size, bg='#2a2a2a', fg='white',
                                   troughcolor='#404040', length=150)
        self.size_scale.pack(side='left')

        self.size_label = tk.Label(size_frame, text="100px", bg='#2a2a2a', fg='#cccccc')
        self.size_label.pack(side='left', padx=(10, 0))
        self.text_size.trace('w', lambda *args: self.size_label.config(text=f"{self.text_size.get()}px"))

        # Position and color
        tk.Label(text_tab, text="Position:", bg='#2a2a2a', fg='white',
                 font=('Segoe UI', 10)).grid(row=2, column=0, sticky='w', padx=10, pady=5)

        ttk.Combobox(text_tab, textvariable=self.text_position, state="readonly",
                     values=["bottom", "top", "left", "center"]).grid(row=2, column=1, sticky='w', pady=5)

        tk.Label(text_tab, text="Color:", bg='#2a2a2a', fg='white',
                 font=('Segoe UI', 10)).grid(row=3, column=0, sticky='w', padx=10, pady=5)

        color_frame = tk.Frame(text_tab, bg='#2a2a2a')
        color_frame.grid(row=3, column=1, sticky='w', pady=5)

        tk.Button(color_frame, text="🎨 Choose", command=self.choose_text_color,
                  bg='#505050', fg='white', font=('Segoe UI', 8), relief='flat',
                  padx=10, pady=3).pack(side='left')

        self.color_preview = tk.Label(color_frame, text="●", font=('Segoe UI', 16),
                                      fg='white', bg='#2a2a2a')
        self.color_preview.pack(side='left', padx=(10, 0))

        # Apply to all checkbox
        tk.Checkbutton(text_tab, text="Apply same text to all images",
                       variable=self.apply_to_all, bg='#2a2a2a', fg='white',
                       selectcolor='#404040').grid(row=4, column=0, columnspan=2,
                                                   sticky='w', padx=10, pady=10)

        # Logo settings tab
        logo_tab = tk.Frame(notebook, bg='#2a2a2a')
        notebook.add(logo_tab, text='🏷️ Logo')

        tk.Label(logo_tab, text="Logo Position:", bg='#2a2a2a', fg='white',
                 font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', padx=10, pady=15)

        ttk.Combobox(logo_tab, textvariable=self.logo_position, state="readonly",
                     values=["top-left", "top-right", "bottom-left", "bottom-right"]).grid(
            row=0, column=1, sticky='w', padx=(0, 10), pady=15)

    def create_actions_section(self, parent):
        # Actions frame
        actions_frame = tk.LabelFrame(parent, text="🚀 Actions", font=('Segoe UI', 12, 'bold'),
                                      bg='#2a2a2a', fg='white', bd=1, relief='solid')
        actions_frame.pack(fill='x')

        # Action buttons grid
        btn_grid = tk.Frame(actions_frame, bg='#2a2a2a')
        btn_grid.pack(fill='x', padx=10, pady=10)

        actions = [
            ("🏷️ Add Logo", self.logofy, '#404040'),
            ("📝 Add Text", self.textify, '#505050'),
            ("🔗 Concatenate", self.concatenate, '#606060'),
            ("🖼️ Convert JPG", self.convert_to_jpg, '#707070'),
            ("📏 Resize 512x512", self.resize_images, '#555555'),
            ("✂️ Crop Images", self.show_crop_dialog, '#454545')
        ]

        for i, (text, command, color) in enumerate(actions):
            row, col = i // 3, i % 3
            btn = tk.Button(btn_grid, text=text, command=command, bg=color, fg='white',
                            font=('Segoe UI', 9), relief='flat', padx=15, pady=8)
            btn.grid(row=row, column=col, padx=5, pady=5, sticky='ew')
            btn_grid.grid_columnconfigure(col, weight=1)

    def select_files(self):
        files = filedialog.askopenfilenames(
            title='Select Images',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.gif *.bmp *.tiff')]
        )
        if files:
            self.selected_files = list(files)
            self.file_listbox.delete(0, tk.END)
            for file in files:
                self.file_listbox.insert(tk.END, os.path.basename(file))

    def select_logo(self):
        logo = filedialog.askopenfilename(
            title='Select Logo',
            filetypes=[('Image files', '*.png *.jpg *.jpeg *.gif *.bmp')]
        )
        if logo:
            self.logo_path = logo
            self.logo_status.configure(text=f"🏷️ Logo: {os.path.basename(logo)}")

    def select_output_directory(self):
        directory = filedialog.askdirectory(title='Choose Output Directory')
        if directory:
            self.output_directory = directory
            self.output_status.configure(text=f"📂 Output: {os.path.basename(directory)}")

    def choose_text_color(self):
        color = colorchooser.askcolor(title="Choose Text Color", color='#ffffff')
        if color[0]:
            self.text_color = tuple(int(c) for c in color[0])
            hex_color = f"#{int(color[0][0]):02x}{int(color[0][1]):02x}{int(color[0][2]):02x}"
            self.color_preview.configure(fg=hex_color)

    def get_output_path(self, original_path, prefix="processed"):
        if self.output_directory:
            filename = os.path.basename(original_path)
            name, ext = os.path.splitext(filename)
            return os.path.join(self.output_directory, f"{prefix}_{name}{ext}")
        else:
            dir_path = os.path.dirname(original_path)
            filename = os.path.basename(original_path)
            name, ext = os.path.splitext(filename)
            return os.path.join(dir_path, f"{prefix}_{name}{ext}")

    def logofy(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return
        if not self.logo_path:
            messagebox.showwarning("No Logo", "Please select a logo first!")
            return

        try:
            logo_img = Image.open(self.logo_path).convert("RGBA")
            processed_count = 0

            for file_path in self.selected_files:
                img = Image.open(file_path)
                img_width, img_height = img.size

                # Resize logo to 1/14th of image height
                new_logo_height = img_height // 14
                new_logo_width = int(new_logo_height * logo_img.width / logo_img.height)
                resized_logo = logo_img.resize((new_logo_width, new_logo_height), Image.Resampling.LANCZOS)

                # Calculate position
                margin = 30
                positions = {
                    "top-left": (margin, margin),
                    "top-right": (img_width - new_logo_width - margin, margin),
                    "bottom-left": (margin, img_height - new_logo_height - margin),
                    "bottom-right": (img_width - new_logo_width - margin, img_height - new_logo_height - margin)
                }
                pos = positions[self.logo_position.get()]

                # Enhance and add logo
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.075)

                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                img.paste(resized_logo, pos, resized_logo)

                # Save
                output_path = self.get_output_path(file_path, "logo")
                if output_path.lower().endswith(('.jpg', '.jpeg')):
                    img = img.convert('RGB')
                img.save(output_path)
                processed_count += 1

            messagebox.showinfo("Success", f"✅ Logo added to {processed_count} images!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")

    def textify(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return

        text_input = self.text_entry.get().strip()
        if not text_input:
            messagebox.showwarning("No Text", "Please enter text to add!")
            return

        try:
            # Try to load font
            font_size = self.text_size.get()
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()

            processed_count = 0

            if self.apply_to_all.get():
                for file_path in self.selected_files:
                    self.add_text_to_image(file_path, text_input, font)
                    processed_count += 1
            else:
                text_list = [t.strip() for t in text_input.split(",")]
                for i, file_path in enumerate(self.selected_files):
                    if i < len(text_list) and text_list[i]:
                        self.add_text_to_image(file_path, text_list[i], font)
                        processed_count += 1

            messagebox.showinfo("Success", f"✅ Text added to {processed_count} images!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")

    def add_text_to_image(self, file_path, text, font):
        img = Image.open(file_path)
        draw = ImageDraw.Draw(img)
        img_width, img_height = img.size

        # Calculate text position
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        positions = {
            "bottom": ((img_width - text_width) // 2, img_height - text_height - 50),
            "top": ((img_width - text_width) // 2, 50),
            "center": ((img_width - text_width) // 2, (img_height - text_height) // 2),
            "left": (50, (img_height - text_height) // 2)
        }
        x, y = positions[self.text_position.get()]

        # Draw text with outline
        outline_width = max(1, font.size // 25)
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), text, fill=(0, 0, 0), font=font)

        draw.text((x, y), text, fill=self.text_color, font=font)

        # Save
        output_path = self.get_output_path(file_path, "text")
        img.save(output_path)

    def concatenate(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return

        try:
            images = [Image.open(f) for f in self.selected_files]
            total_width = sum(img.width for img in images) + 30 * (len(images) - 1)
            max_height = max(img.height for img in images)

            combined_img = Image.new('RGB', (total_width, max_height), 'white')

            x_offset = 0
            for img in images:
                combined_img.paste(img, (x_offset, 0))
                x_offset += img.width + 30

            output_path = os.path.join(self.output_directory or os.path.dirname(self.selected_files[0]),
                                       "concatenated_images.png")
            combined_img.save(output_path)
            messagebox.showinfo("Success", "✅ Images concatenated!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")

    def convert_to_jpg(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return

        try:
            for file_path in self.selected_files:
                img = Image.open(file_path).convert("RGB")
                output_path = self.get_output_path(file_path, "jpg")
                output_path = os.path.splitext(output_path)[0] + ".jpg"
                img.save(output_path, "JPEG", quality=95)

            messagebox.showinfo("Success", f"✅ {len(self.selected_files)} images converted to JPG!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")

    def resize_images(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return

        try:
            for file_path in self.selected_files:
                img = Image.open(file_path)
                resized_img = img.resize((512, 512), Image.Resampling.LANCZOS)
                output_path = self.get_output_path(file_path, "resized_512x512")
                resized_img.save(output_path)

            messagebox.showinfo("Success", f"✅ {len(self.selected_files)} images resized!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")

    def show_crop_dialog(self):
        if not self.selected_files:
            messagebox.showwarning("No Images", "Please select images first!")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Crop Settings")
        dialog.geometry("350x250")
        dialog.configure(bg='#2a2a2a')
        dialog.transient(self.root)
        dialog.grab_set()

        # Center dialog
        dialog.geometry(f"+{self.root.winfo_rootx() + 50}+{self.root.winfo_rooty() + 50}")

        tk.Label(dialog, text="✂️ Crop Images", font=('Segoe UI', 14, 'bold'),
                 bg='#2a2a2a', fg='white').pack(pady=20)

        # Dimensions
        dims_frame = tk.Frame(dialog, bg='#2a2a2a')
        dims_frame.pack(pady=10)

        tk.Label(dims_frame, text="Width:", bg='#2a2a2a', fg='white').grid(row=0, column=0, padx=5)
        width_var = tk.IntVar(value=500)
        tk.Entry(dims_frame, textvariable=width_var, width=8, bg='#404040', fg='white').grid(row=0, column=1, padx=5)

        tk.Label(dims_frame, text="Height:", bg='#2a2a2a', fg='white').grid(row=0, column=2, padx=5)
        height_var = tk.IntVar(value=500)
        tk.Entry(dims_frame, textvariable=height_var, width=8, bg='#404040', fg='white').grid(row=0, column=3, padx=5)

        # Position
        tk.Label(dialog, text="Crop from:", bg='#2a2a2a', fg='white').pack(pady=(20, 5))
        position_var = tk.StringVar(value="center")

        pos_frame = tk.Frame(dialog, bg='#2a2a2a')
        pos_frame.pack()

        for i, (text, value) in enumerate([("Center", "center"), ("Top-Left", "top-left"),
                                           ("Top-Right", "top-right"), ("Bottom-Left", "bottom-left"),
                                           ("Bottom-Right", "bottom-right")]):
            tk.Radiobutton(pos_frame, text=text, variable=position_var, value=value,
                           bg='#2a2a2a', fg='white', selectcolor='#404040').pack(anchor='w')

        # Buttons
        btn_frame = tk.Frame(dialog, bg='#2a2a2a')
        btn_frame.pack(pady=20)

        def perform_crop():
            try:
                width, height = width_var.get(), height_var.get()
                if width <= 0 or height <= 0:
                    messagebox.showerror("Invalid", "Width and height must be positive!")
                    return
                self.crop_images(width, height, position_var.get())
                dialog.destroy()
            except ValueError:
                messagebox.showerror("Invalid", "Please enter valid numbers!")

        tk.Button(btn_frame, text="✂️ Crop", command=perform_crop, bg='#505050', fg='white',
                  relief='flat', padx=15, pady=5).pack(side='left', padx=5)
        tk.Button(btn_frame, text="❌ Cancel", command=dialog.destroy, bg='#404040', fg='white',
                  relief='flat', padx=15, pady=5).pack(side='left', padx=5)

    def crop_images(self, crop_width, crop_height, position):
        try:
            for file_path in self.selected_files:
                img = Image.open(file_path)
                img_width, img_height = img.size

                # Calculate crop position
                positions = {
                    "center": ((img_width - crop_width) // 2, (img_height - crop_height) // 2),
                    "top-left": (0, 0),
                    "top-right": (img_width - crop_width, 0),
                    "bottom-left": (0, img_height - crop_height),
                    "bottom-right": (img_width - crop_width, img_height - crop_height)
                }

                left, top = positions[position]
                left = max(0, min(left, img_width - crop_width))
                top = max(0, min(top, img_height - crop_height))

                cropped_img = img.crop((left, top, left + crop_width, top + crop_height))
                output_path = self.get_output_path(file_path, f"cropped_{crop_width}x{crop_height}")
                cropped_img.save(output_path)

            messagebox.showinfo("Success", f"✅ {len(self.selected_files)} images cropped!")

        except Exception as e:
            messagebox.showerror("Error", f"❌ Error: {str(e)}")


def main():
    root = tk.Tk()
    app = ImageProcessingTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()

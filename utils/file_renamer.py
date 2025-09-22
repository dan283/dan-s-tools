#!/usr/bin/env python3
"""
File Manager GUI Tool
A comprehensive file management utility with renaming, numbering, and search/replace functionality.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import re
import shutil
from pathlib import Path


class FileManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("File Manager - Rename, Number & Search/Replace")
        self.root.geometry("800x600")
        self.root.configure(bg='#f0f0f0')

        # Variables
        self.selected_folder = tk.StringVar()
        self.files_list = []

        self.setup_ui()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(4, weight=1)

        # Folder selection
        folder_frame = ttk.LabelFrame(main_frame, text="Select Folder", padding="5")
        folder_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))
        folder_frame.columnconfigure(1, weight=1)

        ttk.Button(folder_frame, text="Browse", command=self.browse_folder).grid(row=0, column=0, padx=(0, 5))
        ttk.Entry(folder_frame, textvariable=self.selected_folder, state="readonly").grid(row=0, column=1,
                                                                                          sticky=(tk.W, tk.E),
                                                                                          padx=(0, 5))
        ttk.Button(folder_frame, text="Refresh", command=self.refresh_files).grid(row=0, column=2)

        # Notebook for different operations
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # Tab 1: Rename Files
        rename_frame = ttk.Frame(notebook, padding="10")
        notebook.add(rename_frame, text="Rename Files")
        self.setup_rename_tab(rename_frame)

        # Tab 2: Number Files
        number_frame = ttk.Frame(notebook, padding="10")
        notebook.add(number_frame, text="Number Files")
        self.setup_number_tab(number_frame)

        # Tab 3: Search & Replace
        search_frame = ttk.Frame(notebook, padding="10")
        notebook.add(search_frame, text="Search & Replace")
        self.setup_search_tab(search_frame)

        # Files list
        list_frame = ttk.LabelFrame(main_frame, text="Files in Selected Folder", padding="5")
        list_frame.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Treeview for files
        self.tree = ttk.Treeview(list_frame, columns=('Original', 'New'), show='headings', height=10)
        self.tree.heading('Original', text='Original Name')
        self.tree.heading('New', text='Preview New Name')
        self.tree.column('Original', width=300)
        self.tree.column('New', width=300)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=3, pady=(10, 0))

        ttk.Button(button_frame, text="Preview Changes", command=self.preview_changes).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Apply Changes", command=self.apply_changes, style="Accent.TButton").pack(
            side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Clear Preview", command=self.clear_preview).pack(side=tk.LEFT)

    def setup_rename_tab(self, parent):
        # Rename options
        ttk.Label(parent, text="Find:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.find_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.find_var, width=40).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(5, 0),
                                                                     pady=(0, 5))

        ttk.Label(parent, text="Replace with:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.replace_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.replace_var, width=40).grid(row=1, column=1, sticky=(tk.W, tk.E),
                                                                        padx=(5, 0), pady=(0, 5))

        # Options
        options_frame = ttk.LabelFrame(parent, text="Options", padding="5")
        options_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        self.case_sensitive = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Case sensitive", variable=self.case_sensitive).grid(row=0, column=0,
                                                                                                 sticky=tk.W)

        self.regex_mode = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Use regular expressions", variable=self.regex_mode).grid(row=0, column=1,
                                                                                                      sticky=tk.W,
                                                                                                      padx=(20, 0))

        parent.columnconfigure(1, weight=1)

    def setup_number_tab(self, parent):
        # Numbering options
        ttk.Label(parent, text="Prefix:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.prefix_var = tk.StringVar(value="File_")
        ttk.Entry(parent, textvariable=self.prefix_var, width=20).grid(row=0, column=1, sticky=tk.W, padx=(5, 0),
                                                                       pady=(0, 5))

        ttk.Label(parent, text="Start number:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.start_num_var = tk.StringVar(value="1")
        ttk.Entry(parent, textvariable=self.start_num_var, width=10).grid(row=1, column=1, sticky=tk.W, padx=(5, 0),
                                                                          pady=(0, 5))

        ttk.Label(parent, text="Number padding:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        self.padding_var = tk.StringVar(value="3")
        ttk.Entry(parent, textvariable=self.padding_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=(5, 0),
                                                                        pady=(0, 5))

        # Numbering options
        options_frame = ttk.LabelFrame(parent, text="Options", padding="5")
        options_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        self.keep_extension = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Keep original extension", variable=self.keep_extension).grid(row=0,
                                                                                                          column=0,
                                                                                                          sticky=tk.W)

        self.sort_files = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Sort files alphabetically", variable=self.sort_files).grid(row=0, column=1,
                                                                                                        sticky=tk.W,
                                                                                                        padx=(20, 0))

        parent.columnconfigure(1, weight=1)

    def setup_search_tab(self, parent):
        # Search and replace in file contents
        ttk.Label(parent, text="Search for text:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.search_text_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.search_text_var, width=40).grid(row=0, column=1, sticky=(tk.W, tk.E),
                                                                            padx=(5, 0), pady=(0, 5))

        ttk.Label(parent, text="Replace with:").grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        self.replace_text_var = tk.StringVar()
        ttk.Entry(parent, textvariable=self.replace_text_var, width=40).grid(row=1, column=1, sticky=(tk.W, tk.E),
                                                                             padx=(5, 0), pady=(0, 5))

        ttk.Label(parent, text="File types:").grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        self.file_types_var = tk.StringVar(value="*.txt,*.py,*.html,*.css,*.js")
        ttk.Entry(parent, textvariable=self.file_types_var, width=40).grid(row=2, column=1, sticky=(tk.W, tk.E),
                                                                           padx=(5, 0), pady=(0, 5))

        # Options for text search
        options_frame = ttk.LabelFrame(parent, text="Options", padding="5")
        options_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))

        self.text_case_sensitive = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Case sensitive", variable=self.text_case_sensitive).grid(row=0, column=0,
                                                                                                      sticky=tk.W)

        self.whole_words = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="Whole words only", variable=self.whole_words).grid(row=0, column=1,
                                                                                                sticky=tk.W,
                                                                                                padx=(20, 0))

        # Action button for text search
        ttk.Button(parent, text="Search & Replace in Files", command=self.search_replace_text).grid(row=4, column=0,
                                                                                                    columnspan=2,
                                                                                                    pady=(10, 0))

        parent.columnconfigure(1, weight=1)

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder.set(folder)
            self.refresh_files()

    def refresh_files(self):
        folder = self.selected_folder.get()
        if not folder or not os.path.exists(folder):
            return

        self.files_list = []
        try:
            for item in os.listdir(folder):
                item_path = os.path.join(folder, item)
                if os.path.isfile(item_path):
                    self.files_list.append(item)

            # Update the treeview
            for item in self.tree.get_children():
                self.tree.delete(item)

            for filename in sorted(self.files_list):
                self.tree.insert('', 'end', values=(filename, ''))

        except Exception as e:
            messagebox.showerror("Error", f"Failed to read folder: {str(e)}")

    def preview_changes(self):
        if not self.files_list:
            messagebox.showwarning("Warning", "No files selected. Please choose a folder first.")
            return

        notebook = self.root.nametowidget(self.root.winfo_children()[0].winfo_children()[1])
        current_tab = notebook.select()
        tab_text = notebook.tab(current_tab, "text")

        # Clear existing preview
        for item in self.tree.get_children():
            filename = self.tree.item(item)['values'][0]
            self.tree.item(item, values=(filename, ''))

        if tab_text == "Rename Files":
            self.preview_rename()
        elif tab_text == "Number Files":
            self.preview_numbering()

    def preview_rename(self):
        find_text = self.find_var.get()
        replace_text = self.replace_var.get()

        if not find_text:
            messagebox.showwarning("Warning", "Please enter text to find.")
            return

        for item in self.tree.get_children():
            original_name = self.tree.item(item)['values'][0]

            try:
                if self.regex_mode.get():
                    flags = 0 if self.case_sensitive.get() else re.IGNORECASE
                    new_name = re.sub(find_text, replace_text, original_name, flags=flags)
                else:
                    if self.case_sensitive.get():
                        new_name = original_name.replace(find_text, replace_text)
                    else:
                        # Case insensitive replace
                        pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                        new_name = pattern.sub(replace_text, original_name)

                self.tree.item(item, values=(original_name, new_name))
            except re.error as e:
                messagebox.showerror("Regex Error", f"Invalid regular expression: {str(e)}")
                return

    def preview_numbering(self):
        try:
            start_num = int(self.start_num_var.get())
            padding = int(self.padding_var.get())
        except ValueError:
            messagebox.showerror("Error", "Start number and padding must be integers.")
            return

        prefix = self.prefix_var.get()
        files_to_process = []

        for item in self.tree.get_children():
            original_name = self.tree.item(item)['values'][0]
            files_to_process.append(original_name)

        if self.sort_files.get():
            files_to_process.sort()

        for i, item in enumerate(self.tree.get_children()):
            original_name = self.tree.item(item)['values'][0]
            file_index = files_to_process.index(original_name)
            number = str(start_num + file_index).zfill(padding)

            if self.keep_extension.get():
                name, ext = os.path.splitext(original_name)
                new_name = f"{prefix}{number}{ext}"
            else:
                new_name = f"{prefix}{number}"

            self.tree.item(item, values=(original_name, new_name))

    def apply_changes(self):
        folder = self.selected_folder.get()
        if not folder:
            messagebox.showwarning("Warning", "No folder selected.")
            return

        changes = []
        for item in self.tree.get_children():
            values = self.tree.item(item)['values']
            if len(values) >= 2 and values[1]:  # Has preview
                original = values[0]
                new_name = values[1]
                if original != new_name:
                    changes.append((original, new_name))

        if not changes:
            messagebox.showinfo("Info", "No changes to apply.")
            return

        # Confirm changes
        if not messagebox.askyesno("Confirm", f"Apply {len(changes)} file rename(s)?"):
            return

        success_count = 0
        errors = []

        for original, new_name in changes:
            try:
                old_path = os.path.join(folder, original)
                new_path = os.path.join(folder, new_name)

                if os.path.exists(new_path):
                    errors.append(f"'{new_name}' already exists")
                    continue

                os.rename(old_path, new_path)
                success_count += 1
            except Exception as e:
                errors.append(f"Failed to rename '{original}': {str(e)}")

        # Show results
        message = f"Successfully renamed {success_count} file(s)."
        if errors:
            message += f"\n\nErrors:\n" + "\n".join(errors)

        if errors:
            messagebox.showwarning("Partial Success", message)
        else:
            messagebox.showinfo("Success", message)

        # Refresh the file list
        self.refresh_files()

    def clear_preview(self):
        for item in self.tree.get_children():
            filename = self.tree.item(item)['values'][0]
            self.tree.item(item, values=(filename, ''))

    def search_replace_text(self):
        folder = self.selected_folder.get()
        if not folder:
            messagebox.showwarning("Warning", "No folder selected.")
            return

        search_text = self.search_text_var.get()
        replace_text = self.replace_text_var.get()

        if not search_text:
            messagebox.showwarning("Warning", "Please enter text to search for.")
            return

        # Parse file types
        file_types = [ext.strip() for ext in self.file_types_var.get().split(',')]

        files_processed = 0
        replacements_made = 0
        errors = []

        try:
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)

                if not os.path.isfile(file_path):
                    continue

                # Check if file matches any of the specified types
                if not any(filename.lower().endswith(ftype.replace('*', '').lower()) for ftype in file_types):
                    continue

                try:
                    # Read file
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()

                    original_content = content

                    # Perform replacement
                    if self.whole_words.get():
                        pattern = r'\b' + re.escape(search_text) + r'\b'
                        flags = 0 if self.text_case_sensitive.get() else re.IGNORECASE
                        content = re.sub(pattern, replace_text, content, flags=flags)
                    elif self.text_case_sensitive.get():
                        content = content.replace(search_text, replace_text)
                    else:
                        # Case insensitive replace
                        pattern = re.compile(re.escape(search_text), re.IGNORECASE)
                        content = pattern.sub(replace_text, content)

                    # Write back if changed
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        replacements_made += original_content.count(
                            search_text) if self.text_case_sensitive.get() else len(
                            re.findall(re.escape(search_text), original_content, re.IGNORECASE))

                    files_processed += 1

                except Exception as e:
                    errors.append(f"Error processing '{filename}': {str(e)}")

        except Exception as e:
            messagebox.showerror("Error", f"Failed to process folder: {str(e)}")
            return

        # Show results
        message = f"Processed {files_processed} file(s).\nMade {replacements_made} replacement(s)."
        if errors:
            message += f"\n\nErrors:\n" + "\n".join(errors[:5])  # Show first 5 errors
            if len(errors) > 5:
                message += f"\n... and {len(errors) - 5} more errors."

        if errors:
            messagebox.showwarning("Completed with Errors", message)
        else:
            messagebox.showinfo("Search & Replace Complete", message)


def main():
    root = tk.Tk()
    app = FileManagerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

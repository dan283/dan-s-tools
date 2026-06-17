import os
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# -----------------------------
# Helpers
# -----------------------------

def scan_subfolders(path, recursive=False):
    result = []

    if recursive:
        for root, dirs, _ in os.walk(path):
            rel = os.path.relpath(root, path)
            if rel == ".":
                continue
            result.append(rel)
    else:
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir():
                    result.append(entry.name)

    return sorted(result)


def build_tree_from_list(folder_list):
    tree = {}
    for folder in folder_list:
        parts = folder.split(os.sep)
        node = tree
        for part in parts:
            node = node.setdefault(part, {})
    return tree


def tree_to_list(tree, prefix=""):
    result = []
    for k, v in tree.items():
        path = f"{prefix}{k}"
        result.append(path)
        result.extend(tree_to_list(v, path + os.sep))
    return result


def create_structure(base_path, folders):
    for folder in folders:
        full_path = os.path.join(base_path, folder)
        os.makedirs(full_path, exist_ok=True)


# -----------------------------
# App
# -----------------------------

class FolderManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Folder Structure Manager")
        self.root.geometry("980x600")

        self.presets = {}  # name -> list of folders
        self.current_preset = None
        self.current_structure = []

        self.setup_ui()

    # ---------------- UI ----------------

    def setup_ui(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Top frame
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=5)

        ttk.Button(top, text="Scan Folder", command=self.scan_folder).pack(side="left")
        ttk.Button(top, text="Import JSON", command=self.import_json).pack(side="left", padx=5)
        ttk.Button(top, text="Export JSON", command=self.export_json).pack(side="left", padx=5)
        ttk.Button(top, text="Create Structure", command=self.create_structure_ui).pack(side="left", padx=5)

        # Preset dropdown
        ttk.Label(top, text="Preset:").pack(side="left", padx=10)

        self.preset_var = tk.StringVar()
        self.preset_dropdown = ttk.Combobox(top, textvariable=self.preset_var, state="readonly")
        self.preset_dropdown.pack(side="left")
        self.preset_dropdown.bind("<<ComboboxSelected>>", self.load_preset)

        ttk.Button(top, text="Save Preset", command=self.save_preset).pack(side="left", padx=5)
        ttk.Button(top, text="Delete", command=self.delete_preset).pack(side="left")

        # Middle layout
        mid = ttk.PanedWindow(self.root, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=10, pady=10)

        # Left panel (list)
        left = ttk.Frame(mid)
        mid.add(left, weight=1)

        ttk.Label(left, text="Folder Structure").pack(anchor="w")

        self.listbox = tk.Listbox(left)
        self.listbox.pack(fill="both", expand=True)

        btns = ttk.Frame(left)
        btns.pack(fill="x")

        ttk.Button(btns, text="Add", command=self.add_folder).pack(side="left")
        ttk.Button(btns, text="Remove", command=self.remove_folder).pack(side="left", padx=5)
        ttk.Button(btns, text="Clear", command=self.clear_structure).pack(side="left")

        # Right panel (tree view)
        right = ttk.Frame(mid)
        mid.add(right, weight=1)

        ttk.Label(right, text="Tree Preview").pack(anchor="w")

        self.tree = ttk.Treeview(right)
        self.tree.pack(fill="both", expand=True)

    # ---------------- Core Logic ----------------

    def scan_folder(self):
        path = filedialog.askdirectory()
        if not path:
            return

        recursive = messagebox.askyesno("Scan Mode", "Scan recursively?")
        self.current_structure = scan_subfolders(path, recursive)

        self.refresh_list()
        self.refresh_tree()

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for f in self.current_structure:
            self.listbox.insert(tk.END, f)

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())

        tree = build_tree_from_list(self.current_structure)

        def insert(parent, node):
            for k, v in node.items():
                item = self.tree.insert(parent, "end", text=k)
                insert(item, v)

        insert("", tree)

    # ---------------- Folder Editing ----------------

    def add_folder(self):
        name = simple_input(self.root, "Add Folder", "Folder path (e.g. assets/models):")
        if name:
            self.current_structure.append(name)
            self.refresh_list()
            self.refresh_tree()

    def remove_folder(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            self.current_structure.pop(i)
        self.refresh_list()
        self.refresh_tree()

    def clear_structure(self):
        self.current_structure = []
        self.refresh_list()
        self.refresh_tree()

    # ---------------- Presets ----------------

    def save_preset(self):
        name = simple_input(self.root, "Preset Name", "Enter preset name:")
        if not name:
            return

        self.presets[name] = list(self.current_structure)
        self.update_dropdown()

    def load_preset(self, _=None):
        name = self.preset_var.get()
        if name in self.presets:
            self.current_structure = list(self.presets[name])
            self.refresh_list()
            self.refresh_tree()

    def delete_preset(self):
        name = self.preset_var.get()
        if name in self.presets:
            del self.presets[name]
            self.update_dropdown()

    def update_dropdown(self):
        self.preset_dropdown["values"] = list(self.presets.keys())

    # ---------------- JSON ----------------

    def export_json(self):
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if not path:
            return

        data = {
            "presets": self.presets,
            "current": self.current_structure
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        messagebox.showinfo("Export", "Saved successfully.")

    def import_json(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return

        with open(path, "r") as f:
            data = json.load(f)

        self.presets = data.get("presets", {})
        self.current_structure = data.get("current", [])

        self.update_dropdown()
        self.refresh_list()
        self.refresh_tree()

    # ---------------- Create Structure ----------------

    def create_structure_ui(self):
        path = filedialog.askdirectory()
        if not path:
            return

        if not self.current_structure:
            messagebox.showwarning("Empty", "No structure loaded.")
            return

        create_structure(path, self.current_structure)
        messagebox.showinfo("Done", "Folder structure created.")


# -----------------------------
# Simple Input Dialog
# -----------------------------

def simple_input(root, title, prompt):
    win = tk.Toplevel(root)
    win.title(title)
    win.geometry("300x120")
    win.grab_set()

    ttk.Label(win, text=prompt).pack(pady=10)
    entry = ttk.Entry(win)
    entry.pack(fill="x", padx=10)

    result = {"value": None}

    def submit():
        result["value"] = entry.get().strip()
        win.destroy()

    ttk.Button(win, text="OK", command=submit).pack(pady=10)

    win.wait_window()
    return result["value"]


# -----------------------------
# Run
# -----------------------------

if __name__ == "__main__":
    root = tk.Tk()
    app = FolderManagerApp(root)
    root.mainloop()

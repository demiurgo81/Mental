import tkinter as tk
from tkinter import ttk

# Función recursiva que procesa el texto y crea el árbol
def parse_tree(tree, parent_node, lines, level=0):
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            i += 1
            continue

        current_level = line.count('#')
        content = line.lstrip('#').strip()

        if current_level == level + 1:
            node = tree.insert(parent_node, 'end', text=content, open=True)
            i += 1
            # Recursivamente agregar hijos del mismo nivel actual
            i += parse_tree(tree, node, lines[i:], level + 1)
        elif current_level <= level:
            return i
        else:
            i += 1
    return i

# Cargar contenido del archivo FINAL_IADER.txt
def load_markmap_data(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = []
        for line in file:
            stripped = line.strip()
            if stripped and not stripped.startswith('<!--') and not stripped.startswith('-->'):
                lines.append(stripped)
        return lines

# Crear ventana principal
def create_gui(tree_data):
    root = tk.Tk()
    root.title("Mapa Mental Interactivo")
    root.geometry("800x600")

    # Configurar estilo del Treeview
    style = ttk.Style()
    style.configure("Treeview", rowheight=25)

    tree = ttk.Treeview(root)
    tree.pack(fill='both', expand=True, padx=10, pady=10)

    # Barra de desplazamiento
    scrollbar = ttk.Scrollbar(root, orient="vertical", command=tree.yview)
    scrollbar.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scrollbar.set)

    # Nodo raíz
    parse_tree(tree, "", tree_data)

    root.mainloop()

if __name__ == "__main__":
    file_path = "FINAL_IADER.txt"  # Asegúrate de tener este archivo en el directorio correcto
    data_lines = load_markmap_data(file_path)
    create_gui(data_lines)
import json
import pathlib
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


DEFAULT_MARKDOWN = """---\nmarkmap:\n  initialExpandLevel: 1\n  color: \"#2563eb\"\n---\n# Catalogo base\n\n## Ejemplo\n- Idea principal\n  - Detalle 1\n  - Detalle 2\n"""


HTML_TEMPLATE = """<!doctype html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<meta http-equiv="X-UA-Compatible" content="ie=edge" />
<title>Mapa mental</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/markmap-toolbar@0.18.12/dist/style.css">
<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
html, body {
  width: 100%;
  height: 100%;
}
body {
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f8fafc;
  color: #0f172a;
  overflow: hidden;
}
#mindmap {
  display: block;
  width: 100vw;
  height: 100vh;
}
#showMarkdownBtn {
  position: absolute;
  top: 20px;
  left: 20px;
  z-index: 1000;
  padding: 12px 18px;
  border: none;
  border-radius: 9999px;
  background: #2563eb;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.25);
  transition: transform 150ms ease, box-shadow 150ms ease;
}
#showMarkdownBtn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.35);
}
#showMarkdownBtn:active {
  transform: translateY(0);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.35);
}
.markdown-modal {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(4px);
  z-index: 1500;
}
.markdown-modal.visible {
  display: flex;
}
.markdown-modal__dialog {
  width: min(900px, 100%);
  max-height: 90vh;
  overflow: hidden;
  border-radius: 18px;
  background: #ffffff;
  color: #0f172a;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.35);
  display: flex;
  flex-direction: column;
}
.markdown-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  background: rgba(37, 99, 235, 0.08);
}
.markdown-modal__title {
  font-size: 18px;
  font-weight: 600;
}
.markdown-modal__close {
  appearance: none;
  border: none;
  border-radius: 9999px;
  width: 32px;
  height: 32px;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  background: rgba(37, 99, 235, 0.12);
  color: #2563eb;
  transition: background 150ms ease, transform 150ms ease;
}
.markdown-modal__close:hover {
  background: rgba(37, 99, 235, 0.2);
  transform: scale(1.05);
}
.markdown-modal__body {
  padding: 24px;
  overflow-y: auto;
  flex: 1 1 auto;
  font-size: 15px;
  line-height: 1.6;
}
.markdown-modal__body pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "Fira Code", "Cascadia Code", "Consolas", monospace;
  font-size: 14px;
  line-height: 1.5;
  color: inherit;
  background: rgba(15, 23, 42, 0.06);
  padding: 18px;
  border-radius: 12px;
}
.markmap-toolbar {
  background: rgba(15, 23, 42, 0.72);
  border-radius: 9999px;
  backdrop-filter: blur(6px);
  padding: 6px 10px;
}
.markmap-toolbar button {
  color: #f8fafc;
}
@media (max-width: 640px) {
  #showMarkdownBtn {
    left: 50%;
    transform: translateX(-50%);
  }
  #showMarkdownBtn:hover {
    transform: translate(-50%, -1px);
  }
}
@media (prefers-color-scheme: dark) {
  body {
    background: #020617;
    color: #e2e8f0;
  }
  #showMarkdownBtn {
    background: #1d4ed8;
    box-shadow: 0 12px 28px rgba(30, 64, 175, 0.35);
  }
  .markdown-modal__dialog {
    background: #0f172a;
    color: #e2e8f0;
  }
  .markdown-modal__header {
    background: rgba(37, 99, 235, 0.18);
    border-bottom-color: rgba(71, 85, 105, 0.35);
  }
  .markdown-modal__body pre {
    background: rgba(15, 23, 42, 0.35);
  }
}
</style>
</head>
<body>
<button id="showMarkdownBtn" type="button">Ver Markdown</button>
<svg id="mindmap" role="img" aria-label="Mapa mental generado"></svg>
<div id="markdownModal" class="markdown-modal" role="dialog" aria-modal="true" aria-labelledby="markdownModalTitle">
  <div class="markdown-modal__dialog">
    <div class="markdown-modal__header">
      <h2 id="markdownModalTitle" class="markdown-modal__title">Markdown original</h2>
      <button id="closeMarkdownBtn" class="markdown-modal__close" type="button" aria-label="Cerrar ventana">&times;</button>
    </div>
    <div class="markdown-modal__body">
      <pre id="markdownViewer"></pre>
    </div>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markmap-view@0.18.12/dist/browser/index.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markmap-toolbar@0.18.12/dist/index.js"></script>
<script src="https://cdn.jsdelivr.net/npm/markmap-lib@0.18.12/dist/browser/index.iife.js"></script>
<script>
(() => {
  const markdownText = __MARKDOWN_JSON__;
  const rootElement = document.getElementById("mindmap");
  if (!rootElement) return;

  const markmapGlobal = window.markmap || {};
  const { Markmap, Toolbar, Transformer, deriveOptions } = markmapGlobal;
  if (!Markmap || !Toolbar || !Transformer) {
    console.error("No se pudieron cargar las bibliotecas de Markmap.");
    return;
  }

  const transformer = new Transformer();
  const { root, frontmatter } = transformer.transform(markdownText);
  const fmOptions = (frontmatter && frontmatter.markmap) || {};
  const options = typeof deriveOptions === "function" ? deriveOptions(fmOptions) : fmOptions;
  const mm = Markmap.create("svg#mindmap", options || {}, root);
  mm.fit();

  const toolbar = new Toolbar();
  const toolbarNode = toolbar.render();
  toolbarNode.style.position = "absolute";
  toolbarNode.style.bottom = "20px";
  toolbarNode.style.right = "20px";
  document.body.append(toolbarNode);
  toolbar.attach(mm);

  const showMarkdownBtn = document.getElementById("showMarkdownBtn");
  const markdownModal = document.getElementById("markdownModal");
  const markdownViewer = document.getElementById("markdownViewer");
  const closeMarkdownBtn = document.getElementById("closeMarkdownBtn");

  const openModal = () => {
    if (markdownViewer) {
      markdownViewer.textContent = markdownText;
    }
    markdownModal.classList.add("visible");
  };

  const closeModal = () => {
    markdownModal.classList.remove("visible");
  };

  showMarkdownBtn?.addEventListener("click", openModal);
  closeMarkdownBtn?.addEventListener("click", closeModal);
  markdownModal?.addEventListener("click", (event) => {
    if (event.target === markdownModal) {
      closeModal();
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && markdownModal.classList.contains("visible")) {
      closeModal();
    }
  });
})();
</script>
</body>
</html>
"""


def build_html(markdown_text: str) -> str:
  markdown_json = json.dumps(markdown_text)
  return HTML_TEMPLATE.replace("__MARKDOWN_JSON__", markdown_json)


class MarkmapGeneratorApp:
  def __init__(self, root: tk.Tk) -> None:
    self.root = root
    self.root.title("Generador de Markmap")
    self.root.geometry("960x720")

    self.output_path = tk.StringVar(value=str(self.default_output_path()))

    main_frame = ttk.Frame(root, padding=20)
    main_frame.pack(fill=tk.BOTH, expand=True)

    header = ttk.Label(
      main_frame,
      text="Pega el Markdown que deseas convertir en un Markmap interactivo con visor de texto integrado.",
      wraplength=860,
      justify=tk.LEFT,
    )
    header.pack(fill=tk.X, pady=(0, 12))

    text_frame = ttk.Frame(main_frame)
    text_frame.pack(fill=tk.BOTH, expand=True)

    self.markdown_text = tk.Text(
      text_frame,
      wrap=tk.NONE,
      font=("Consolas", 11),
      undo=True,
    )
    self.markdown_text.insert("1.0", DEFAULT_MARKDOWN)
    self.markdown_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    scrollbar_y = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.markdown_text.yview)
    scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
    self.markdown_text.configure(yscrollcommand=scrollbar_y.set)

    path_frame = ttk.Frame(main_frame)
    path_frame.pack(fill=tk.X, pady=(16, 8))

    ttk.Label(path_frame, text="Archivo HTML de salida:").pack(side=tk.LEFT)
    path_entry = ttk.Entry(path_frame, textvariable=self.output_path, width=70)
    path_entry.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

    ttk.Button(path_frame, text="Explorar...", command=self.ask_output_path).pack(side=tk.LEFT)

    button_frame = ttk.Frame(main_frame)
    button_frame.pack(fill=tk.X, pady=(8, 0))

    ttk.Button(button_frame, text="Cargar Markdown...", command=self.load_markdown).pack(side=tk.LEFT)
    ttk.Button(button_frame, text="Generar Markmap", command=self.generate_html).pack(side=tk.RIGHT)

  def default_output_path(self) -> pathlib.Path:
    docs_dir = pathlib.Path.cwd() / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    return docs_dir / "markmap_interactivo.html"

  def ask_output_path(self) -> None:
    initial_dir = pathlib.Path(self.output_path.get()).parent
    file_path = filedialog.asksaveasfilename(
      parent=self.root,
      title="Guardar Markmap como...",
      defaultextension=".html",
      filetypes=(("Archivos HTML", "*.html"), ("Todos los archivos", "*.*")),
      initialdir=initial_dir,
      initialfile=pathlib.Path(self.output_path.get()).name,
    )
    if file_path:
      self.output_path.set(file_path)

  def load_markdown(self) -> None:
    file_path = filedialog.askopenfilename(
      parent=self.root,
      title="Selecciona un archivo Markdown",
      filetypes=(("Archivos Markdown", "*.md;*.markdown"), ("Todos los archivos", "*.*")),
    )
    if not file_path:
      return
    try:
      content = pathlib.Path(file_path).read_text(encoding="utf-8")
    except OSError as exc:
      messagebox.showerror("Error al leer", f"No se pudo leer el archivo:\\n{exc}")
      return

    self.markdown_text.delete("1.0", tk.END)
    self.markdown_text.insert("1.0", content)

  def generate_html(self) -> None:
    markdown = self.markdown_text.get("1.0", tk.END).strip()
    if not markdown:
      messagebox.showwarning("Markdown vacio", "Agrega contenido en Markdown antes de generar el Markmap.")
      return

    output_path = pathlib.Path(self.output_path.get())
    try:
      html_content = build_html(markdown)
      output_path.write_text(html_content, encoding="utf-8")
    except OSError as exc:
      messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo HTML:\\n{exc}")
      return

    messagebox.showinfo("Markmap creado", f"Archivo guardado en:\\n{output_path}")


def main() -> None:
  root = tk.Tk()
  app = MarkmapGeneratorApp(root)
  root.mainloop()


if __name__ == "__main__":
  main()

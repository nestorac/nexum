-- filtros/pj.lua
-- Convierte cada sección "## Nombre" en una ficha: imagen izquierda + texto derecha (minipage).
-- Estructura esperada (típica):
--   ## Nombre
--   ![](img/pj/nombre.jpg)
--   ...texto y/o listas...
--
-- Si no hay imagen, deja el contenido tal cual (con salto de página opcional).

local cfg = {
  -- Anchuras de columnas (suma <= 0.98 recomendado si hay \hfill)
  img_col_w   = "0.34\\textwidth",
  text_col_w  = "0.62\\textwidth",
  img_w       = "\\linewidth",

  -- Espacio mínimo antes de la ficha para evitar cortes feos
  needspace   = "10\\baselineskip",

  -- Insertar salto de página antes de cada ficha excepto la primera
  clearpage_between = true,

  -- Render del título del PJ
  title_cmd_prefix  = "\\textbf{",
  title_cmd_suffix  = "}\\par\\medskip\n",
}

-- Ocultar título principal (# ...) y su primer párrafo
local skip_h1 = true
local skipping_intro = false

local function is_header2(block)
  return block.t == "Header" and block.level == 2
end

local function stringify_inlines(inlines)
  return pandoc.utils.stringify(inlines)
end

-- Busca la primera imagen en una lista de bloques.
-- Devuelve: (src, new_blocks_sin_esa_imagen, found)
local function extract_first_image(blocks)
  for bi, b in ipairs(blocks) do
    if b.t == "Para" or b.t == "Plain" then
      local new_inlines = {}
      local found_src = nil

      for _, inl in ipairs(b.content) do
        if (not found_src) and inl.t == "Image" then
          found_src = inl.src
        else
          table.insert(new_inlines, inl)
        end
      end

      if found_src then
        local new_blocks = {}
        for i = 1, bi - 1 do
          table.insert(new_blocks, blocks[i])
        end

        if #new_inlines > 0 then
          local new_b = (b.t == "Para") and pandoc.Para(new_inlines) or pandoc.Plain(new_inlines)
          table.insert(new_blocks, new_b)
        end

        for i = bi + 1, #blocks do
          table.insert(new_blocks, blocks[i])
        end

        return found_src, new_blocks, true
      end
    end
  end

  return nil, blocks, false
end

-- Renderiza una lista de bloques como LaTeX usando el escritor de Pandoc
local function blocks_to_latex(blocks, meta)
  local doc = pandoc.Pandoc(blocks, meta)
  return pandoc.write(doc, "latex")
end

function Pandoc(doc)
  local out = {}
  local i = 1
  local first_card = true

  while i <= #doc.blocks do
    local b = doc.blocks[i]

    -- Eliminar el título principal (# ...) y el texto inmediatamente debajo
    if skip_h1 then
      if b.t == "Header" and b.level == 1 then
        skipping_intro = true
        i = i + 1
        goto continue
      end

      if skipping_intro and (b.t == "Para" or b.t == "Plain") then
        skip_h1 = false
        skipping_intro = false
        i = i + 1
        goto continue
      end
    end

    if is_header2(b) then
      local title = stringify_inlines(b.content)

      -- Recolectar bloques del PJ hasta el siguiente Header nivel 2 o final
      local content_blocks = {}
      local j = i + 1
      while j <= #doc.blocks and not is_header2(doc.blocks[j]) do
        table.insert(content_blocks, doc.blocks[j])
        j = j + 1
      end

      -- Extraer primera imagen del bloque
      local img_src, content_wo_img, has_img = extract_first_image(content_blocks)

      if cfg.clearpage_between and not first_card then
        table.insert(out, pandoc.RawBlock("latex", "\\clearpage\n"))
      end
      first_card = false

      if not has_img then
        table.insert(out, pandoc.RawBlock("latex", "\\Needspace{" .. cfg.needspace .. "}\n"))
        table.insert(out, pandoc.Header(2, b.content, b.attr))
        for _, cb in ipairs(content_blocks) do
          table.insert(out, cb)
        end
        i = j
      else
        local latex_body = blocks_to_latex(content_wo_img, doc.meta)

        local latex = ""
        latex = latex .. "\\Needspace{" .. cfg.needspace .. "}\n"
        latex = latex .. "\\noindent\n"
        latex = latex .. "\\begin{minipage}[t]{" .. cfg.img_col_w .. "}\n"
        latex = latex .. "\\vspace{0pt}\n"
        latex = latex .. "\\centering\n"
        latex = latex .. "\\includegraphics[width=" .. cfg.img_w .. "]{" .. img_src .. "}\n"
        latex = latex .. "\\end{minipage}\\hfill\n"
        latex = latex .. "\\begin{minipage}[t]{" .. cfg.text_col_w .. "}\n"
        latex = latex .. "\\vspace{0pt}\n"
        latex = latex .. cfg.title_cmd_prefix .. title .. cfg.title_cmd_suffix
        latex = latex .. latex_body .. "\n"
        latex = latex .. "\\end{minipage}\n"

        table.insert(out, pandoc.RawBlock("latex", latex))
        i = j
      end
    else
      table.insert(out, b)
      i = i + 1
    end

    ::continue::
  end

  return pandoc.Pandoc(out, doc.meta)
end

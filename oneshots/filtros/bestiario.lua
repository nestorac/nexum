-- filtros/bestiario.lua
-- Cada ### + imagen + texto -> una ficha (media página A4)

local cards = {}
local current = nil

local function stringify_inlines(inlines)
  return pandoc.utils.stringify(pandoc.Span(inlines))
end

local function para_to_latex(el)
  -- convierte un párrafo a LaTeX inline sin envolver en entorno
  local doc = pandoc.Pandoc({ el })
  local latex = pandoc.write(doc, "latex")
  -- quitar posibles \n finales y el wrapping de párrafo si molesta
  latex = latex:gsub("^%s+", ""):gsub("%s+$", "")
  return latex
end

local function flush()
  if not (current and current.title) then
    current = nil
    return
  end

  local img = current.img or "img/monstruos/placeholder.jpg"
  local body = table.concat(current.body, "\n\n")
  if body == "" then
    body = "\\textit{(sin descripción)}"
  end

  -- Importante: RawBlock "latex" para que no se escape
  local latex = string.format(
    "\\ficha{%s}{%s}{%%\n%s\n}",
    img,
    current.title:gsub("([#%%_])", "\\%1"), -- escape mínimo del título
    body
  )
  table.insert(cards, pandoc.RawBlock("latex", latex))
  current = nil
end

function Header(el)
  if el.level == 3 then
    flush()
    current = {
      title = stringify_inlines(el.content),
      img = nil,
      body = {}
    }
    return {} -- consumir encabezado
  end
  -- ignorar H1/H2 en el PDF de fichas
  if el.level <= 2 then
    return {}
  end
end

function Para(el)
  if not current then
    return {}
  end

  -- imagen sola en el párrafo: ![alt](ruta)
  if #el.content == 1 and el.content[1].t == "Image" then
    current.img = el.content[1].src
    return {}
  end

  table.insert(current.body, para_to_latex(el))
  return {}
end

function BulletList(el)
  if not current then return {} end
  local latex = pandoc.write(pandoc.Pandoc({ el }), "latex")
  table.insert(current.body, latex)
  return {}
end

function OrderedList(el)
  if not current then return {} end
  local latex = pandoc.write(pandoc.Pandoc({ el }), "latex")
  table.insert(current.body, latex)
  return {}
end

function Pandoc(doc)
  flush()
  -- Solo devolvemos las fichas. La definición de \ficha va en metadata_bestiario.yaml
  return pandoc.Pandoc(cards, doc.meta)
end

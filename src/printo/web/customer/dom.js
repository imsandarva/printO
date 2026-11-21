/* Tiny DOM helpers. User text always goes through textContent. */

export function el(tag, props) {
  const node = document.createElement(tag);
  const options = props || {};
  if (options.class) node.className = options.class;
  if (options.text != null) node.textContent = options.text;
  if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) node.setAttribute(key, value);
  if (tag === "button" && !node.hasAttribute("type")) node.type = "button";
  return node;
}

export function icon(markup) {
  const holder = document.createElement("template");
  holder.innerHTML = markup.trim();
  return holder.content.firstElementChild;
}

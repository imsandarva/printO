/* Small DOM helpers for the counter. */

export function el(tag, props) {
  const node = document.createElement(tag);
  const options = props || {};
  if (options.class) node.className = options.class;
  if (options.text != null) node.textContent = options.text;
  if (options.attrs) for (const [key, value] of Object.entries(options.attrs)) if (value != null) node.setAttribute(key, value);
  if (options.disabled) node.disabled = true;
  if (options.on) for (const [key, fn] of Object.entries(options.on)) node.addEventListener(key, fn);
  if (tag === "button") node.type = "button";
  return node;
}

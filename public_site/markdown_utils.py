import bleach
import markdown

ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "br", "hr",
    "strong", "em", "b", "i", "u", "s", "del",
    "a", "img",
    "ul", "ol", "li",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "th", "td",
    "div", "span",
    "details", "summary",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "class"],
    "th": ["align"],
    "td": ["align"],
    "div": ["class"],
    "span": ["class"],
    "code": ["class"],
    "pre": ["class"],
}


def render_markdown(text: str) -> str:
    """Convert markdown to sanitised HTML. No scripts, no iframes."""
    html = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "toc", "nl2br"],
    )
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )

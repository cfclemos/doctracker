# How to document code for doctracker

doctracker builds the technical reference of this project by reading the code
statically (it never imports or runs it). Everything shown in the wiki comes from
the code itself: names, signatures, type hints, decorators and docstrings. Follow
these rules so every entity gets a complete page.

## Settings of this project

- Docstring style: **{docstring_style}** (`docstring_style` in `doc/config/config.json`).
- Private members (`_name`): **{private_members}** (`show_private`).

## What to document

1. **Every module and package** starts with a module docstring: one summary line,
   then a short paragraph saying what the module is for. A package's docstring goes
   in its `__init__.py`.
2. **Every public class, function and method** has a docstring.
3. **Type hints on every parameter and return value.** The wiki shows them in the
   signature and in the parameters table; do not repeat types inside the docstring
   unless the hint is missing.
4. **Module-level constants and class attributes** get a docstring written as a
   string literal on the line right after the assignment:

   ```python
   DEFAULT_UNITS: Units = Units.METRIC
   """Units used when the caller does not choose any."""
   ```

   Instance attributes set in `__init__` (and dataclass fields) are documented in
   the class docstring's `Attributes` section instead.
5. **Public API of a package:** list it in `__all__`; the wiki shows it on the
   package page.

## Docstring layout

- First line: one sentence, imperative mood for functions ("Fetch the forecast…"),
  ending with a period. It is used as the summary in lists and search results.
- Blank line, then any longer explanation (Markdown is rendered).
- Then the sections below, in this order. Leave out the sections that do not apply.

| Section | When |
|---|---|
| Args | every parameter, including `*args` and `**kwargs` |
| Returns / Yields | what is returned or yielded, and what it means |
| Raises | every exception the caller should expect, and when |
| Attributes | instance attributes and dataclass fields (class docstrings) |
| Examples | short `>>>` sessions; they are shown as code |
| Note / Warning | anything the caller must not miss |

## Example in the {docstring_style} style

```python
{example}
```

## Things to avoid

- Docstrings that only repeat the name ("Get weather." for `get_weather`).
- Describing the implementation instead of the behavior; the wiki already shows the source.
- Parameters missing from `Args`: the table shows "-" in their description.
- Raw HTML in docstrings: it is escaped, not rendered.

# libsed2 Python API notes (for the translator)

Surveyed against `libsed2-0.1.1-py3-none-any.whl` (Python 3.13); re-checked against the wheel of 2026-10-08 (same
version number, newer build: ParameterScan `.model`, chained and comma bracket indexing, indexed aliases).  Everything below was
exercised against real documents unless marked "not yet checked".  The library is
generated; do not edit it.  Anything the translator needs that is missing is a gap: do not work around it, skip what needs it, and record it in a new `GAPS.md` (see build.md).

## Loading, writing, validating

```python
import libsed2
doc = libsed2.read_from_file("test.sed2.json")        # or read_from_string(text)
problems = doc.validate()                             # list of ValidationProblem, empty if valid
for p in problems:
    p.rule_id, p.severity, p.location, p.message      # e.g. 'SEDBase-0006', 'error', '/tasks/s/input'
libsed2.write_to_file(doc, "out.sed2.json")           # or write_to_string(doc); doc.to_json_value()
```

* Parsing a well-formed JSON file that has semantic errors (e.g. an unresolved reference) does not raise; call
  `validate()` and check the list.  Malformed JSON itself raises the usual `json` error.
  `severity` can be "error" or "warning"; a translator should refuse documents with errors.
* A valid document round-trips exactly (`doc.to_json_value() == json.load(file)`), key order included.
* `ApiError` is raised for API misuse (reading an unset field), never for invalid documents.
* Rule text for each problem is in `ValidationProblem.rule`.

## Walking the document

* `doc.get_constants()`, `doc.get_tasks()`, `doc.get_outputs()` return ids in document order.
  Items: `doc.get_constants_item(id)` (raw JSON value: number, string, list, dict),
  `doc.get_tasks_item(id)`, `doc.get_outputs_item(id)`.
* Task and output objects are instances of the concrete classes (`ExplicitODESimulation`,
  `ModelImport`, `Report`, ...).  `obj.get_type()` returns the `_type` string
  (`"explicitODESimulation"`).  A namespaced `_type` from an unknown prefix comes back as an opaque
  `Unknown<Base>` object that round-trips unchanged.
* `obj.get_id()` returns the element's id, the key it has in its parent collection (tasks, outputs, a
  Loop's sub-tasks, a plot's curves, ...).  It raises `ApiError` for an element that is not stored under a
  key (a nested range, a detached element).  Constants are raw values, so they have no element and no
  `get_id`.  `obj.get_parent()` returns the owning element or the document (for a task directly in
  `tasks` it returns the `SEDDocument`, not the collection).  `obj.get_document()` returns the document.
* Nested collections (e.g. a `Loop`'s sub-tasks, a plot's curves) use the same collection pattern
  (`loop.get_sub_tasks()`, `loop.get_sub_tasks_item(id)`); checked for sub-tasks and curves.

## Reading attributes

* Plain attribute: `get_<name>()`, `is_set_<name>()`.
* "OrRef" attributes (a literal or a `#...` reference): `is_<name>_ref()`, `get_<name>_ref()`,
  `get_<name>_value()`.  Example: `sim.is_independent_variable_ref()` is False and
  `sim.get_independent_variable_value()` is `"time"`.
* Embedded range objects: `sim.get_independent_variable_range()` returns a `NumericRange` (etc.)
  with `get_start_value()`, `get_end_value()`, `get_values_value()`, `get_scale_value()`, ...
* Collections of children use `get_<name>()` for ids and `get_<name>_item(id)` plus add/insert/remove.
* Every element has `name`, `description`, `notes`, `annotations`, and namespace attributes
  (`get_namespace_attribute(prefix, key)`).

## References

All public, in `libsed2`:

* `libsed2.is_reference(text)` is True for a string that parses as a `#...` reference.
* `libsed2.parse_reference("#tasks:sim1.model['S1']")` returns a `ParsedReference` with `collection`
  ('tasks'), `path` (['sim1']) and `accessors` (`[('dot','model'), ('index', RefIndex(kind='label', value='S1'))]`).
  Index kinds are `int`, `label` and `range`; each `RefIndex` has `same_bracket` (True for the second and later
  indices written in one pair of brackets, `[a:b, n]`).  Pure syntax: it never raises, and it ignores text after
  the point where parsing stops, so check `is_reference` and `validate()` first.
* `libsed2.get_sed_reference(doc, ref)` returns `(target, resolved_path)`: the element for `#tasks:`,
  `#outputs:` and `#styles:` references, the constant's raw value for `#constants:`.
* `libsed2.get_reference_value(doc, ref)` evaluates a `#constants:` reference with its bracket indices applied
  (following a constant that is itself a reference).  It raises `ApiError` for anything that is not a constant.
* `libsed2.apply_indices(value, accessors)` applies bracket indices (`[1]`, `[-1]`, `[0:2]`, `['key']`) to any
  literal JSON value.  A label index needs a dictionary; a list has no labels.  Dot-accessors (`.a`, `.loc`,
  `.isel`, `.sel`) are rejected on literals (SEDBase-0008).
* Accessors on run-time results (a task's or output's AnnotatedData) are applied by the translator's runtime,
  because libsed2 does not hold results.

## Output shapes

* `libsed2.outputs_shape` exposes `resolve_output(outputs_json, fields, accessors, shape_of)`,
  `resolve_dims`, `eval_expr` (the `expr`/`valid` mini-language of `outputs.json`), and
  `index_into_literal`.  Not yet checked against real task documents; revisit in P2.3.

## Math

```python
node = libsed2.parse_math("1 + sin(a)*pow(b, 2) / #tasks:sim1[0]")   # ASTNode
node.to_string()                      # canonical text
for n in node.walk(): n.node_type, n.name, n.text, n.children
```

* Node types: NUMBER, REFERENCE, NAME, FUNCTION_CALL, ARRAY, UMINUS, UPLUS, ADD, SUB, MUL, DIV, POW.
  Relational and logical operators and everything else are FUNCTION_CALL nodes (`eq`, `and`,
  `piecewise`, `sin`, ...).
* `libsed2._predefined_functions` has `FUNCTIONS` (name -> allowed arities) and `CONSTANTS`
  (`exponentiale`, `notanumber`, `false`, `pi`, `true`, `infinity`).  It carries arities only; the
  category and source metadata in `SED2/schema/predefined-functions.json` are not in the wheel.
  The translator must define each function's semantics itself; a test compares its function table with `SED2/schema/predefined-functions.json`.
* Syntax errors raise `MathSyntaxError`.

## Mapping translator needs to libsed2 calls

| Translator step | libsed2 support |
|---|---|
| Parse and validate input | `read_from_file`, `validate()` (full) |
| Document-order walk | `get_constants/tasks/outputs()` ids, `*_item(id)` |
| Identify task kind | `get_type()` / `isinstance` |
| Read attributes (literal or reference) | `get_x_value()`, `get_x_ref()`, `is_x_ref()` |
| Resolve a reference to an element or constant | `get_sed_reference`, `get_reference_value` |
| Apply index/label/slice accessors | to constants and literals: `apply_indices`; to run-time results: translator runtime |
| Shape of a task's output | `outputs_shape.resolve_output` (to verify) |
| Math to Python | `parse_math` AST; semantics of each function by the translator |
| Element id | `obj.get_id()` |

## Repeats, plots and other attributes (checked in P2.13-P2.17)

* Loop / Scatter / ParameterScan: `task.get_sub_tasks()` and `get_sub_tasks_item(id)`; `task.get_range()` (Loop,
  Scatter), `task.get_parameter_ranges()` (list; each has `get_model_element_value()`), `task.get_loop_variables()`
  and `get_loop_variables_item(name)` with `get_initial_value()` (the raw JSON value, a reference string or a literal)
  and `get_subsequent_values()` (a reference string).  `outputVariableMap` is read like any OrRef attribute
  (`get_output_variable_map_value()` is a dict of references).
* Reference forms inside a repeat: `#tasks:rep:subTasks:id` (and `...:id.model`, `...:id['S1']`),
  `#tasks:loop:loopVariables:name` (parse_reference gives `path=['loop','loopVariables','name']`), and the dotted
  per-iteration outputs `#tasks:rep.range`, `.index`, `.ranges['k']`, `.indexes['k']`, and a ParameterScan's `.model`
  (`#tasks:scan.model`; the colon form `#tasks:scan:model` does not validate); the dotted form of a sub-task (`#tasks:rep.subTasks.x`) is rejected by design.
* A `math` string is always an expression (Calculation description), but libsed2's getters report one that begins
  with `#` as a reference: `is_math_ref()` is true and `get_math_value()` raises, so the translator reads the text with
  `get_math_ref()` (GAPS.md G-005).
* Attribute getters with several words are snake case: `get_set_values_value()`, `is_set_set_values()`,
  `get_x_error_lower()`, `get_right_y_axis()`.  Plot types are `plot2D` and `plot3D`; `plot.get_curves()` /
  `get_surfaces()` list ids in document order; Axis attributes are OrRef (`get_scale_value()`, `get_min_value()`, ...).

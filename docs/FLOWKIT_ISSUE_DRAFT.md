# Issue 草稿：提交给 FlowKit（whitews/flowkit）

> 用途：作为 FlowGate 作者向上游 FlowKit 提交 issue/PR。
> 全部内容来自我们在真实数据（8_color_data_set）上的探查实证，可直接粘贴。
> 提交后把 issue 链接加进 README 的"致谢/上游"段，简历上可写"contributed upstream to FlowKit"。

---

## [Docs] PNS labels are empty in the 8-color tutorial dataset, making pnn/pns disambiguation confusing

**Describe the bug**
In the official tutorial dataset `data/8_color_data_set/fcs_files/*.fcs`
(e.g. `101_DEN084Y5_15_E01_008_clean.fcs`), all `$PNS` keywords are empty
strings. `Sample.pns_labels` therefore returns `['', '', ...]`, while
`Sample.pnn_labels` returns full names such as `"TNFa FITC FLR-A"` and
`detectors` returns the same names.

For downstream tools that rely on `pns_labels` to distinguish the
*fluorescent* channel name from the *stain* name (e.g. building a
spillover matrix with `Matrix(data, detectors, fluorochromes=...)`),
this makes the tutorial data unusable as an example, because there is no
fluorochrome name to pass.

**To reproduce**

```python
from flowkit import Sample
s = Sample("data/8_color_data_set/fcs_files/101_DEN084Y5_15_E01_008_clean.fcs")
print(s.pns_labels[:3])   # ['', '', '']
print(s.pnn_labels[:3])   # ['FSC-A', 'SSC-A', 'Time'] / fluorescence names
print(s.detectors[:3])
```

**Expected**
Either the FCS files carry proper `$PNS` values, or the tutorial docs note
that `pns_labels` is empty and `detectors`/`pnn_labels` should be used as
the fluorochrome source.

**Environment**
- flowkit version: 1.3.2
- flowio version: 1.4.0
- Python: 3.12
- OS: Windows 11

---

## [Docs] `Matrix.__init__` infers fluorochromes from detectors when omitted, but this is undocumented

**Describe the bug**
`Matrix(data, detectors)` works and silently uses `detectors` as
`fluorochromes` when the optional argument is omitted. The docstring
signature in the README shows `fluorochromes=None` but does not state the
fallback behaviour. Tools that callers write by passing an explicit
empty list (as suggested by the signature) produce a matrix with empty
fluorochrome names, which then serializes to GatingML
(`<data-type:fluorochrome></data-type:fluorochrome>`).

**Suggestion**
Document that when `fluorochromes=None`, the matrix reuses `detectors`;
and when it is provided, lengths must match `detectors`.

---

## [Docs] `$SPILLOVER` appears in `sample.get_metadata()` under lowercase key "spillover"

**Describe the bug**
FCS 3.1 specifies the keyword as `$SPILLOVER`, but in
`sample.get_metadata()` the key is stored lowercased (`"spillover"`).
`extract_compensation_matrices` handles this internally, but any caller
reading metadata directly may look for `$SPILLOVER` and miss it.

**Suggestion**
Document the lowercase key in `get_metadata()` docstring, or expose a
constant. (Not a functional bug since the matrix extraction path works.)

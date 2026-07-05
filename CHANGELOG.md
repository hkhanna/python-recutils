# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-05

A comprehensive audit against the GNU recutils manual (version 1.9), making
the library a faithful implementation of the rec format and its utilities.
The test suite grew from 252 to 480 tests, most derived directly from the
manual's examples.

### Added

- **Date input formats** (manual chapter 20): a `parse_datetime` implementation
  supporting calendar dates (ISO 8601, US `MONTH/DAY/YEAR`, literal months in
  every documented order), times of day with meridians and time zone
  corrections, time zone items, ISO combined date/time items, days of the week,
  relative items (`1 year ago`, `tomorrow`, ...), pure numbers (`YYYYMMDD` /
  `HHMM`) and seconds since the Epoch (`@N`). Timestamps without an explicit
  zone correction are interpreted as UTC. Exported as `parse_datetime`.
- **`recfmt`** (manual chapter 14): formats records using templates with
  `{{...}}` slots holding selection expressions, one copy per record.
- **`rec2csv` and `csv2rec`** (manual section 15.1): CSV conversion using the
  manual's header-building algorithm (`FIELDNAME[_N]`, duplicates removed,
  missing fields as empty columns).
- **External and remote descriptors** (manual chapter 9): `%rec: Type SOURCE`
  descriptors are fetched from a file or URL and merged for constraint and type
  information; disable with `no_external=True`.
- **`recins`, `recdel`, `recset`, `recinf`** brought to full parity with their
  command-line counterparts, including replacement mode, in-place commenting,
  field-expression targeting, and descriptor summaries.
- Backtracking evaluation of selection expressions over every permutation of
  same-named fields (manual section 3.5.4), real chronological date operators
  (`<<`, `>>`, `==`), and `evaluate_sex_value` for computing an expression's
  value.
- Password-verifiable encryption of `%confidential` fields, so decrypting with
  a wrong password leaves the data encrypted (manual chapter 13).
- `RecSyntaxError` and `ExternalDescriptorError` (both `ValueError` subclasses)
  are exported.

### Changed

- Selection-expression semantics now follow the manual: ordering operators
  compare numerically (string comparison is reserved for `=`), non-numeric
  operands fail evaluation rather than coercing to zero, integer division and
  modulus truncate toward zero, and a predicate's final value treats reals and
  strings as false.
- `recsel` output and selection align with the manual: mutually exclusive
  selection options, `-c` incompatible with the print options, inner joins that
  run before the selection expression, type-aware sorting and grouping,
  GNU-style aggregate formatting, and confidential-field decryption with a
  password.
- `recinf` emits the documented `N Type` summary (bare count for anonymous
  record sets), with names-only and descriptor output modes.
- The parser reports syntactical errors with their line number instead of
  silently dropping lines.

### Fixed

- Numerous correctness fixes surfaced during review: external descriptors are
  no longer written back into edited files, join expressions can reference
  joined fields, `recset` field-expression subscripts are resolved against the
  unmodified record, `recdel` refuses pervasive deletes without `force`, and
  several date-parsing edge cases (`next DAY`, dotted meridians, out-of-range
  years).
- README corrections for the `recfix` option flags and examples.

## [0.1.3] - 2025-12-27

### Removed

- Foreign key referential integrity validation from `recfix()`. The GNU recutils `recfix` command does not validate that foreign key values exist in referenced record sets; the `rec` type is only used for type checking and joins. This change aligns our implementation with the reference behavior.

## [0.1.2] - 2025-12-27

### Changed

- Minor update to developer ergonomics and README.

## [0.1.1] - 2025-12-27

### Added

- ~~Foreign key validation in `recfix()`: validates that `%type: Field rec OtherType` references exist in the referenced record set's key field~~ (removed in later release)
- Typedef loop detection: detects circular references in `%typedef` chains (e.g., `A -> B -> C -> A`)
- Undefined type detection: reports errors when `%typedef` or `%type` declarations reference undefined types

## [0.1.0] - 2025-12-26

### Added

- Initial release
- `parse_records()` function for parsing rec format files
- `recsel()` function for querying records with selection expressions
- `recfix()` function for validating and fixing records
- Support for record descriptors with field types and constraints
- Selection expression support (comparison, logical, membership operators)

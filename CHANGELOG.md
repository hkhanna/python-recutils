# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2025-12-27

### Changed

- Minor update to developer ergonomics and README.

## [0.1.1] - 2025-12-27

### Added

- Foreign key validation in `recfix()`: validates that `%type: Field rec OtherType` references exist in the referenced record set's key field
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

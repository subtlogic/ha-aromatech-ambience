# Changelog

## 0.5.0 — unreleased

First standalone release.

- Domain renamed from `ambience` to `aromatech_ambience`. Installs of the
  earlier private build must remove the old integration and add this one.
- The Bluetooth frame trace moved from a sensor attribute to the diagnostics
  download, so it is no longer written to the recorder on every poll.
- The master switch is named "Scenting" instead of "Diffuser", so it does not
  read as a second strength control beside Intensity.
- Added diagnostics, and brand images: a stylised capsule diffuser icon plus
  light and dark logos. They are our own drawings, deliberately not
  AromaTech's artwork or lettering.

## 0.4.3

- Light: Off is selectable as an effect alongside Warm, Cool and Flow.

## 0.4.2

- Schedule writes retry up to three times, each confirmed against a fresh
  device report, and fail explicitly if the device keeps the old value.

## 0.4.1

- Schedule writes send the four-byte continuation fragment. Without it the
  device ignored intensity and schedule edits.
- A bare turn-on after Off selects Warm instead of Custom black.
- Light replies update state immediately.

## 0.4.0

- A missed advertisement at boot no longer fails setup; entities stay
  unavailable until the first successful poll.

## 0.3.x

- Greet the device with a time sync before any command on a new link.
- Stop writing the device's status bytes back as part of a schedule command.
- Frame trace ring buffer for diagnosing ignored writes.

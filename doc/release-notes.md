## 0.4.0-beta.1

Initial public pre-release for OnePlus 15T (PLZ110), LineageOS `24.0-20261011-NIGHTLY-fairlady` only.

- Correct repeated crop metadata scaling for independently opened physical rear cameras 2 and 3, including quantized 10× and CUSTOM still requests.
- Toggle with Magisk Action; retain the requested state across reboot.
- Validate exact firmware/library identities and disable correction on a detected fault.
- Construct the patched image from the verified installed original; no complete system image is distributed.

Logical-camera automatic lens selection and application post-processing are outside this patch. Install this beta manually; automatic updates start with stable releases.

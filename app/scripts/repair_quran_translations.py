"""Retired unsafe import repair entry point.

The old command flattened footnote markers into source words and mislabeled
translation resource 20 as 131. Use the evidence-checked repair command; its
read-only preview is the default and applying requires a new rollback file.
"""
def run_repair():
    raise RuntimeError('Use scripts/repair_quran_annotations.py --help for an audited repair. No records were changed.')

if __name__ == '__main__':
    run_repair()

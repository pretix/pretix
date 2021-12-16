def clean_filename(fname):
    """
    hierarkey.forms.SettingsForm appends a random value to every filename. However, it keeps the
    extension around "twice". Tis leads to:

    "Terms.pdf" → "Terms.pdf.OybgvyAH.pdf"

    In pretix Hosted, our storage layer also adds a hash of the file to the filename, so we have

    "Terms.pdf" → "Terms.pdf.OybgvyAH.22c0583727d5bc.pdf"

    This function reverses this operation:

    "Terms.pdf.OybgvyAH.22c0583727d5bc.pdf" → "Terms.pdf"
    """
    ext = fname.split('.')[-1]
    return fname.rsplit(ext, 2)[0] + ext

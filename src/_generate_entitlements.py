"""
Script to generate the entitlements.plist file
"""

import os
import plistlib


plist = dict.fromkeys(
    (
        "com.apple.security.cs.allow-jit",
        "com.apple.security.cs.allow-unsigned-executable-memory",
        "com.apple.security.cs.disable-executable-page-protection",
        "com.apple.security.cs.disable-library-validation",
        "com.apple.security.cs.allow-dyld-environment-variables",
    ),
    True
)


here = os.path.dirname(__file__)
with open(os.path.join(here, "entitlements.plist"), "wb") as f:
    plistlib.dump(plist, f)

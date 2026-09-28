# FG Link 1.6.8 hardened release rules.
#
# R8 minification/optimization is intentionally enabled for the public APK.
# Mapping files stay private and must never be included in public release assets.

-repackageclasses 'f'
-allowaccessmodification
-adaptclassstrings
-renamesourcefileattribute SourceFile

# Preserve metadata commonly required by AndroidX/ML Kit while allowing app code
# names and implementation details to be minified.
-keepattributes *Annotation*,Signature,InnerClasses,EnclosingMethod

# Remove Android log calls from optimized release bytecode.
-assumenosideeffects class android.util.Log {
    public static *** v(...);
    public static *** d(...);
    public static *** i(...);
    public static *** w(...);
    public static *** e(...);
}

@echo off
echo start cmd...
pushd "%~dp0"
"C:\Program Files\Autodesk\Maya2026\bin\maya.exe" -batch ^
    -command "python(\"exec(open('create_proxy.py').read())\")"
popd
echo finish cmd...
pause
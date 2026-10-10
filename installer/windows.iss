; Compilar desde la raíz: ISCC /DAppVersion=<n> installer\windows.iss
#ifndef AppVersion
  #define AppVersion "0"
#endif

[Setup]
AppName=Monterrey Count
AppVersion={#AppVersion}
; Ruta del usuario y sin admin: el actualizador reemplaza {app} sin permisos elevados.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MonterreyCount
DefaultGroupName=Monterrey Count
DisableProgramGroupPage=yes
; Fuera de {app}: el actualizador reemplaza {app} completo y borraría unins000.exe.
UninstallFilesDir={localappdata}\Programs\MonterreyCount-uninstall
UninstallDisplayIcon={app}\MonterreyCount.exe
OutputDir=..
OutputBaseFilename=MonterreyCount-Setup
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"

[Files]
Source: "..\dist\MonterreyCount\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Monterrey Count"; Filename: "{app}\MonterreyCount.exe"; Tasks: desktopicon
Name: "{autoprograms}\Monterrey Count"; Filename: "{app}\MonterreyCount.exe"

[Run]
Filename: "{app}\MonterreyCount.exe"; Description: "Abrir Monterrey Count"; Flags: postinstall nowait skipifsilent

; Borra también lo que dejaron las actualizaciones.
[UninstallDelete]
Type: filesandordirs; Name: "{app}"

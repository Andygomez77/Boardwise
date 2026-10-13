; Compilar desde la raíz: ISCC /DAppVersion=<n> installer\windows.iss
#ifndef AppVersion
  #define AppVersion "0"
#endif

[Setup]
AppName=Boardwise
; Fijo para siempre: si cambia, un cambio de nombre visible crearía otra instalación.
AppId=Boardwise
AppVersion={#AppVersion}
; Ruta del usuario y sin admin: el actualizador reemplaza {app} sin permisos elevados.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Boardwise
DefaultGroupName=Boardwise
DisableProgramGroupPage=yes
; Fuera de {app}: el actualizador reemplaza {app} completo y borraría unins000.exe.
UninstallFilesDir={localappdata}\Programs\Boardwise-uninstall
UninstallDisplayIcon={app}\Boardwise.exe
OutputDir=..
OutputBaseFilename=Boardwise-Setup
Compression=lzma2
SolidCompression=yes

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"

[Files]
Source: "..\dist\Boardwise\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\Boardwise"; Filename: "{app}\Boardwise.exe"; Tasks: desktopicon
Name: "{autoprograms}\Boardwise"; Filename: "{app}\Boardwise.exe"

[Run]
Filename: "{app}\Boardwise.exe"; Description: "Abrir Boardwise"; Flags: postinstall nowait skipifsilent

; Borra también lo que dejaron las actualizaciones.
[UninstallDelete]
Type: filesandordirs; Name: "{app}"

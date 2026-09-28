<#
Copies the humans into a Unity project, under Assets/Humans (the layout MedievalSetting uses):
  unity/Humans/Runtime, Editor, Shaders  -> Assets/Humans/Scripts/Runtime, Scripts/Editor, Shaders
  export/Human_Body.fbx, Human_Hair.fbx  -> Assets/Humans/Models
  export/Textures/*.png                  -> Assets/Humans/Textures
  export/human_face_config.json, human_rig.json -> Assets/Humans/Data
Files are overwritten in place; their .meta files (import settings, references) are kept.
Afterwards, in Unity: Tools > Humans > Rebuild Prefab and Showcase.

Usage:
  powershell -ExecutionPolicy Bypass -File tools\install_to_unity.ps1 -Project E:\Unity\Projects\MedievalSetting
  add -ScriptsOnly to copy only scripts and shaders
#>
param(
    [Parameter(Mandatory = $true)][string]$Project,
    [switch]$ScriptsOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$Project = (Resolve-Path $Project).Path
$assets = Join-Path $Project 'Assets'
if (-not (Test-Path $assets)) { throw "No Assets folder in $Project - is it a Unity project?" }
$dst = Join-Path $assets 'Humans'

function Copy-Into([string]$from, [string]$filter, [string]$to) {
    New-Item -ItemType Directory -Force -Path $to | Out-Null
    $files = @(Get-ChildItem -Path $from -Filter $filter -File)
    foreach ($f in $files) { Copy-Item -LiteralPath $f.FullName -Destination $to -Force }
    Write-Host ("{0,3} x {1,-24} -> {2}" -f $files.Count, $filter, $to.Substring($Project.Length + 1))
}

Copy-Into (Join-Path $root 'unity\Humans\Runtime') '*.cs' (Join-Path $dst 'Scripts\Runtime')
Copy-Into (Join-Path $root 'unity\Humans\Editor') '*.cs' (Join-Path $dst 'Scripts\Editor')
Copy-Into (Join-Path $root 'unity\Humans\Shaders') '*.*' (Join-Path $dst 'Shaders')
if (-not $ScriptsOnly) {
    # garments ship per family (Human_Cloth_<family>.fbx): drop cloth FBXs the export no longer has
    $models = Join-Path $dst 'Models'
    if (Test-Path $models) {
        Get-ChildItem $models -Filter 'Human_Cloth*.fbx' | Where-Object {
            -not (Test-Path (Join-Path (Join-Path $root 'export') $_.Name)) } | ForEach-Object {
            Remove-Item $_.FullName; $meta = $_.FullName + '.meta'; if (Test-Path $meta) { Remove-Item $meta } }
    }
    Copy-Into (Join-Path $root 'export') 'Human_*.fbx' (Join-Path $dst 'Models')
    Copy-Into (Join-Path $root 'export\Textures') '*.png' (Join-Path $dst 'Textures')
    Copy-Into (Join-Path $root 'export') 'human_*.json' (Join-Path $dst 'Data')
    if (Test-Path (Join-Path $root 'export\Anims')) {
        Copy-Into (Join-Path $root 'export\Anims') 'Human@*.fbx' (Join-Path $dst 'Animation\Clips')
    }
}
Write-Host 'Done. In Unity: Tools > Humans > Rebuild Prefab and Showcase'

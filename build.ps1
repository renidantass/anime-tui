#!/usr/bin/env pwsh
# Build script local para Windows (substitui o build v1 manual).
# Gera dist/anishelf.exe com ícone de bandeja funcionando.

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $here) { $here = Get-Location }

$icon = Join-Path $here "icon.ico"
if (-not (Test-Path $icon)) {
    Write-Error "icon.ico nao encontrado na raiz do projeto. Rode o script de geracao do ICO primeiro."
    exit 1
}

uv run pyinstaller `
    --noconfirm --clean --onefile --windowed `
    --name anishelf `
    --icon "$icon" `
    --add-data "app/presentation/web/static:app/presentation/web/static" `
    --hidden-import=textual `
    --hidden-import=textual.app `
    --hidden-import=textual.widgets `
    --hidden-import=textual.containers `
    --hidden-import=textual.screen `
    --hidden-import=rich `
    --hidden-import=bs4 `
    --hidden-import=PIL `
    --hidden-import=PIL.Image `
    --hidden-import=PIL.ImageDraw `
    --hidden-import=PIL.ImageEnhance `
    --hidden-import=PIL.ImageFile `
    --hidden-import=requests `
    --hidden-import=app `
    --hidden-import=app.infrastructure.sources.animesonlinecc `
    --hidden-import=app.infrastructure.sources.animesonlinecloud `
    --hidden-import=app.infrastructure.sources.animeyabu `
    --hidden-import=app.infrastructure.sources.goyabu `
    --hidden-import=app.infrastructure.sources.topanimes `
    --hidden-import=app.infrastructure.sources.source_discovery `
    --hidden-import=pystray `
    --hidden-import=pystray._win32 `
    --hidden-import=pystray._xorg `
    --hidden-import=pystray._gtk `
    --hidden-import=pystray._appindicator `
    --hidden-import=pystray._darwin `
    --hidden-import=pystray._util `
    --collect-submodules=app `
    --exclude-module=pygments `
    --exclude-module=setuptools `
    --exclude-module=pkg_resources `
    --exclude-module=lxml `
    --exclude-module=tkinter `
    --exclude-module=unittest `
    --exclude-module=pydoc `
    --exclude-module=doctest `
    --exclude-module=test `
    --exclude-module=xmlrpc `
    --exclude-module=multiprocessing.popen_spawn_win32 `
    --exclude-module=PIL.AvifImagePlugin `
    --exclude-module=PIL.FtexImagePlugin `
    --exclude-module=PIL.BlpImagePlugin `
    --exclude-module=PIL.McIdasImagePlugin `
    --exclude-module=PIL.MicImagePlugin `
    --exclude-module=PIL.MpegImagePlugin `
    --exclude-module=PIL.Hdf5StubImagePlugin `
    --exclude-module=PIL.DdsImagePlugin `
    --exclude-module=PIL.FliImagePlugin `
    --exclude-module=PIL.GbrImagePlugin `
    --exclude-module=PIL.IcnsImagePlugin `
    --exclude-module=PIL.ImImagePlugin `
    --exclude-module=PIL.ImtImagePlugin `
    --exclude-module=PIL.IptcImagePlugin `
    --exclude-module=PIL.PalmImagePlugin `
    --exclude-module=PIL.PcdImagePlugin `
    --exclude-module=PIL.PdfImagePlugin `
    --exclude-module=PIL.PixarImagePlugin `
    --exclude-module=PIL.PsdImagePlugin `
    --exclude-module=PIL.SgiImagePlugin `
    --exclude-module=PIL.SpiderImagePlugin `
    --exclude-module=PIL.SunImagePlugin `
    --exclude-module=PIL.WalImagePlugin `
    --exclude-module=PIL.WmfImagePlugin `
    --exclude-module=PIL.XbmImagePlugin `
    --exclude-module=PIL.XpmImagePlugin `
    --exclude-module=PIL.XVThumbImagePlugin `
    --exclude-module=PIL.ImageTk `
    --exclude-module=PIL.ImageQt `
    --exclude-module=PIL.ImageShow `
    --exclude-module=PIL._imagingtk `
    --exclude-module=PIL._avif `
    anishelf.py

Write-Host "Build concluido. Executavel em: $(Join-Path $here 'dist' 'anishelf.exe')"

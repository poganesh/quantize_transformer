$ErrorActionPreference = "Stop"
$build_yaml_file = "build.yml"
$download_py_script = "download.py"
$download_temp_folder = "temp_download"
$currentDirectory = $PSScriptRoot

function Invoke-SafeCommand {
    param (
        [ScriptBlock]$Command,
        [string]$action
    )
    Write-Host "Start ${action} ..."
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) {
            Write-Host "$Action failed."
            exit 1
            # Write-Host "execute output: $python_output"
        } else {
            Write-Host "${action} success."
        }
    } catch {
        Write-Host "${action} failed: $($_.Exception.Message)"
        exit 1
    }
}

function Set-Path {
    param ()
    $text = $(pip show onnxruntime-vitisai|findstr Location)
    $pattern = "Location:\s+(.+)"
    $matches = [regex]::Matches($text, $pattern)

    if ($matches.Success) {
        $path = $matches[0].Groups[1].Value
        $env:PATH = "$path\onnxruntime\capi;$env:PATH"
        $env:VAIE_INSTALL_DIR = "$currentDirectory\other_libs_qdq"
        $env:XLNX_ENABLE_CACHE = "0"
        $env:GLOG_minloglevel = "2"
    } else {
        exit 1
    }
}

$functions = @(
    @{ Action = "download and extract dependencies"; Command = { New-Item -Path $download_temp_folder -ItemType Directory -Force; python $download_py_script $build_yaml_file $download_temp_folder } },
    @{ Action = "install tvm wheel"; Command = { cd $download_temp_folder; pip install tvm-0.8.dev0+aie.0.2.5.tar.gz } },
    @{ Action = "install onnxruntime-vitisai wheel"; Command = { cd voe-4.0-win_amd64; pip install --upgrade --force-reinstall onnxruntime_vitisai-1.15.1-cp39-cp39-win_amd64.whl} },
    @{ Action = "install voe wheel"; Command = { pip install --upgrade --force-reinstall voe-0.1.0-cp39-cp39-win_amd64.whl; python installer.py } },
    @{ Action = "replace some files"; Command = { cd ../../replaces; python replace_files.py } },
    @{ Action = "set environment variable"; Command = { cd ..; Set-Path } }
)

foreach ($functionInfo in $functions) {
    $action = $functionInfo.Action
    $command = $functionInfo.Command
    Invoke-SafeCommand -Action $action -Command $command
    
    if (-not $?) {
        Write-Host "Stop build since $action failed."
        break
    }
}

Write-Host "Build bert success, you could run it now."
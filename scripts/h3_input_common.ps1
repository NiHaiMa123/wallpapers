# Shared input-image resolution for the MiniMax H3 runners.
# Dot-source this file, then call Resolve-H3InputImage.
#
# The LoadImage node only accepts names relative to the ComfyUI input directory,
# so an image supplied from anywhere else has to be published into that directory
# first. Publishing never overwrites: an existing same-named file is reused only
# when its SHA-256 matches, otherwise the run is refused.

$H3DefaultComfyInputDir = 'D:\Comfy-Desktop\ComfyUI-Shared\input'
$H3SupportedImageExtensions = @('.png', '.jpg', '.jpeg', '.webp', '.bmp')

function Resolve-H3ComfyInputDir {
    [CmdletBinding()]
    param([string]$ComfyInputDir)

    if ($ComfyInputDir) {
        $dir = $ComfyInputDir
    }
    else {
        $dir = $H3DefaultComfyInputDir
    }
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        throw "ComfyUI input directory was not found: $dir"
    }
    return [IO.Path]::GetFullPath($dir)
}

function Get-H3LoadImageChoices {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Api)

    $info = Invoke-RestMethod -Uri "$Api/object_info/LoadImage"
    $spec = $info.LoadImage.input.required.image
    if (-not $spec -or $spec.Count -lt 1) {
        throw 'ComfyUI did not report any LoadImage file choices.'
    }
    return @($spec[0])
}

function Get-H3ImageTag {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Sha256
    )

    $stem = [IO.Path]::GetFileNameWithoutExtension($Path)
    $safe = ($stem -replace '[^A-Za-z0-9_-]', '')
    if ($safe.Length -gt 24) {
        $safe = $safe.Substring(0, 24)
    }
    if (-not $safe) {
        $safe = 'img' + $Sha256.Substring(0, 8).ToLowerInvariant()
    }
    return $safe
}

function Resolve-H3InputImage {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$InputImage,
        [Parameter(Mandatory)][string]$Api,
        [string]$ComfyInputDir
    )

    $inputRoot = Resolve-H3ComfyInputDir -ComfyInputDir $ComfyInputDir

    # Accept either a filesystem path or a name that already lives in the input directory.
    $source = $null
    if (Test-Path -LiteralPath $InputImage -PathType Leaf) {
        $source = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $InputImage).Path)
    }
    else {
        $candidate = Join-Path $inputRoot $InputImage
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $source = [IO.Path]::GetFullPath($candidate)
        }
    }
    if (-not $source) {
        throw "Input image was not found as a path, nor inside the ComfyUI input directory: $InputImage"
    }

    $extension = [IO.Path]::GetExtension($source).ToLowerInvariant()
    if ($H3SupportedImageExtensions -notcontains $extension) {
        throw "Unsupported image extension '$extension'. Supported: $($H3SupportedImageExtensions -join ', ')"
    }

    $rootWithSeparator = $inputRoot.TrimEnd('\') + '\'
    $published = $false
    if ($source.StartsWith($rootWithSeparator, [StringComparison]::OrdinalIgnoreCase)) {
        $resolvedPath = $source
        $relative = $source.Substring($rootWithSeparator.Length)
    }
    else {
        $leaf = [IO.Path]::GetFileName($source)
        $target = Join-Path $inputRoot $leaf
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
            $targetHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash
            if ($sourceHash -ne $targetHash) {
                throw "A different file named '$leaf' already exists in the ComfyUI input directory. Rename the source image rather than overwriting: $target"
            }
        }
        else {
            Copy-Item -LiteralPath $source -Destination $target
            $published = $true
        }
        $resolvedPath = [IO.Path]::GetFullPath($target)
        $relative = $leaf
    }
    $relative = $relative.Replace('\', '/')

    $choices = Get-H3LoadImageChoices -Api $Api
    if ($choices -notcontains $relative) {
        throw "ComfyUI's LoadImage node does not list '$relative'. Confirm it is a readable image inside $inputRoot."
    }

    $sha256 = (Get-FileHash -LiteralPath $resolvedPath -Algorithm SHA256).Hash
    return [ordered]@{
        load_image_value = $relative
        source_path      = $source
        resolved_path    = $resolvedPath
        input_root       = $inputRoot
        published        = $published
        sha256           = $sha256
        tag              = Get-H3ImageTag -Path $resolvedPath -Sha256 $sha256
    }
}

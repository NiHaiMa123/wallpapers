param(
    [string]$Server = "http://127.0.0.1:8188",
    [string]$InputImage = "keqing_gpt_reference_16x9.png",
    [string]$FilenamePrefix = "krea2/keqing_identity_edit",
    [UInt64]$Seed = 438921706,
    [int]$OutputWidth = 1536,
    [int]$OutputHeight = 864,
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"

$editPrompt = @"
Preserve the exact same adult fictional Keqing character from the reference: identical facial identity, violet eyes, lavender twin-tail hairstyle and hair ornaments, official purple-and-lavender costume patterns, gloves, dark translucent stockings, high heels, body proportions, sword design, and the complete full-body crossed-sword pose. Keep the subject placement, camera angle, silhouette, hands, legs, feet and all costume details unchanged.

Refine only the rendering quality and environment into a premium cinematic Liyue-inspired jade rooftop garden at blue hour after rain. Add layered distant pavilion architecture and mountains, restrained violet Electro particles around the sword, warm carved lantern fill, subtle cool rim light, realistic wet-stone reflections, richer material separation, natural matte skin, clean anime facial planes, detailed eyes and hair, and a sharp high-end 3D anime game CG / refined MMD finish. Keep the character dominant and fully visible from hair tips to both shoes.

No text, logo, watermark, advertisement border, product pedestal, extra people, duplicate limbs, malformed hands, extra fingers, distorted sword, waxy skin, plastic toy appearance, flat lighting, blown highlights, excessive blur or excessive bokeh.
"@

$negativePrompt = "text, logo, watermark, signature, product advertisement, pedestal, extra people, duplicate body, extra limbs, extra fingers, malformed hands, deformed sword, cropped feet, cropped hair, waxy face, plastic doll skin, flat lighting, overexposure, excessive blur, low detail"
$identitySystemPrompt = "Study the reference image closely. Preserve the subject's facial identity, anime facial proportions, violet eyes, lavender twin-tail hair silhouette and ornaments, costume construction and patterns, body proportions, sword, full-body pose, hand placement and camera framing. Treat background and lighting as editable, but do not redesign the character."

$prompt = @{
    "1" = @{ class_type = "UNETLoader"; inputs = @{ unet_name = "Krea2\krea2_turbo_int8_convrot.safetensors"; weight_dtype = "default" } }
    "2" = @{ class_type = "LoraLoaderModelOnly"; inputs = @{ model = @("1", 0); lora_name = "Krea2-功能\Krea2-编辑identity_edit_v1_2.safetensors"; strength_model = 1.0 } }
    "3" = @{ class_type = "CLIPLoader"; inputs = @{ clip_name = "qwen3vl_4b_fp8_scaled.safetensors"; type = "krea2"; device = "default" } }
    "4" = @{ class_type = "VAELoader"; inputs = @{ vae_name = "qwen_image_vae.safetensors" } }
    "5" = @{ class_type = "LoadImage"; inputs = @{ image = $InputImage } }
    "6" = @{ class_type = "ImageScaleToTotalPixels"; inputs = @{ image = @("5", 0); upscale_method = "lanczos"; megapixels = 1.0; resolution_steps = 16 } }
    "7" = @{ class_type = "VAEEncode"; inputs = @{ pixels = @("6", 0); vae = @("4", 0) } }
    "8" = @{ class_type = "EmptySD3LatentImage"; inputs = @{ width = $OutputWidth; height = $OutputHeight; batch_size = 1 } }
    "9" = @{ class_type = "Krea2EditModelPatch"; inputs = @{
            model = @("2", 0)
            source_latent = @("7", 0)
            ref_boost = 4.0
            ref_boost_a = 1.0
            fit_mode = "fit"
            vae = @("4", 0)
            source_image = @("6", 0)
            target_latent = @("8", 0)
        } }
    "10" = @{ class_type = "Krea2EditGroundedEncode"; inputs = @{
            clip = @("3", 0)
            prompt = $editPrompt
            image = @("6", 0)
            grounding_px = 1024
            system_prompt = $identitySystemPrompt
        } }
    "11" = @{ class_type = "Krea2EditGroundedEncode"; inputs = @{
            clip = @("3", 0)
            prompt = $negativePrompt
            image = @("6", 0)
            grounding_px = 1024
            system_prompt = $identitySystemPrompt
        } }
    "12" = @{ class_type = "KSampler"; inputs = @{
            model = @("9", 0)
            seed = $Seed
            steps = 10
            cfg = 1.0
            sampler_name = "euler"
            scheduler = "simple"
            positive = @("10", 0)
            negative = @("11", 0)
            latent_image = @("8", 0)
            denoise = 1.0
        } }
    "13" = @{ class_type = "VAEDecode"; inputs = @{ samples = @("12", 0); vae = @("4", 0) } }
    "14" = @{ class_type = "SaveImage"; inputs = @{ images = @("13", 0); filename_prefix = $FilenamePrefix } }
}

$clientId = [guid]::NewGuid().ToString()
$body = @{ prompt = $prompt; client_id = $clientId } | ConvertTo-Json -Depth 20
$queued = Invoke-RestMethod -Uri "$Server/prompt" -Method Post -ContentType "application/json" -Body $body
if (-not $queued.prompt_id) {
    throw "ComfyUI did not return a prompt_id: $($queued | ConvertTo-Json -Depth 8)"
}

$promptId = [string]$queued.prompt_id
Write-Output "queued_prompt_id=$promptId"
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)

while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    $history = Invoke-RestMethod -Uri "$Server/history/$promptId" -Method Get
    $entry = $history.$promptId
    if ($null -eq $entry) { continue }

    if ($entry.status.status_str -eq "error") {
        $messages = $entry.status.messages | ConvertTo-Json -Depth 12
        throw "ComfyUI execution failed: $messages"
    }

    if ($entry.status.completed -eq $true) {
        $images = @($entry.outputs."14".images)
        if ($images.Count -eq 0) { throw "Workflow completed but SaveImage returned no files." }
        foreach ($image in $images) {
            Write-Output ("output={0}|subfolder={1}|type={2}" -f $image.filename, $image.subfolder, $image.type)
        }
        exit 0
    }
}

throw "Timed out after $TimeoutSeconds seconds waiting for prompt $promptId"

# ===============================
# Twilio Toll-Free Verification
# ===============================

# ---- Twilio credentials (local script only; not committed) ----
$AccountSid = "TODO: Add AccountSid"
$AuthToken  = "TODO: Add AuthToken"

# ---- Required configuration ----
$config = @{
    BusinessName = "TODO: Add BusinessName" # FLAME ONTARIO ARTS COLLECTIVE
    DoingBusinessAs = "TODO: Add DoingBusinessAs" # Sideburn
    BusinessWebsite = "TODO: Add BusinessWebsite" # https://sideburn.ca
    NotificationEmail = "TODO: Add NotificationEmail" # tech@sideburn.ca

    UseCaseCategories = @(
        "TODO: Add UseCaseCategories" # EVENTS
    )

    UseCaseSummary = "Prospective attendees sign up for a waiting list and opt in to receive SMS notifications when their waitlist spot is ready."

    ProductionMessageSample = "Your Sideburn waitlist number is up! Please check your email for details."

    OptInImageUrls = @(
        "TODO: Add image URL" # See Google Drive for image
    )

    OptInType = "WEB_FORM"

    MessageVolume = "1,000"

    TollfreePhoneNumberSid = "TODO: Add TollfreePhoneNumberSid" # Starts with PN

    CustomerProfileSid = "TODO: Add CustomerProfileSid" # Starts with BU - use the secondary customer profile (trust hub)
}

# ---- Recommended compliance fields ----
$config.businessType = "NON_PROFIT"
$config.privacyPolicyUrl = "https://sideburn.ca/privacy-policy/"
$config.optInKeywords = @("START","STOP")

# ---- Business registration (required when Business Type is not SOLE_PROPRIETOR) ----
$config.BusinessRegistrationNumber = "TODO: Add BusinessRegistrationNumber"
$config.BusinessRegistrationAuthority = "PROVINCIAL_NUMBER"   # e.g. CBN (Canada), EIN (US), PROVINCIAL_NUMBER, NEQ (Quebec)
$config.BusinessRegistrationCountry = "CA"     # e.g. CA, US

# ---- API endpoint ----
$uri = "https://messaging.twilio.com/v1/Tollfree/Verifications"

# ---- Build form body (Twilio expects arrays as repeated key=value) ----
function Add-FormField {
    param([System.Collections.ArrayList]$list, [string]$key, [string]$value)
    if ($value -ne "") { [void]$list.Add("$key=$([System.Uri]::EscapeDataString($value))") }
}
$form = [System.Collections.ArrayList]::new()
Add-FormField $form "BusinessName" $config.BusinessName
Add-FormField $form "DoingBusinessAs" $config.DoingBusinessAs
Add-FormField $form "BusinessWebsite" $config.BusinessWebsite
Add-FormField $form "NotificationEmail" $config.NotificationEmail
foreach ($c in $config.UseCaseCategories) { Add-FormField $form "UseCaseCategories" $c }
Add-FormField $form "UseCaseSummary" $config.UseCaseSummary
Add-FormField $form "ProductionMessageSample" $config.ProductionMessageSample
foreach ($u in $config.OptInImageUrls) { Add-FormField $form "OptInImageUrls" $u }
Add-FormField $form "OptInType" $config.OptInType
Add-FormField $form "MessageVolume" $config.MessageVolume
Add-FormField $form "TollfreePhoneNumberSid" $config.TollfreePhoneNumberSid
Add-FormField $form "CustomerProfileSid" $config.CustomerProfileSid
Add-FormField $form "BusinessType" $config.BusinessType
Add-FormField $form "BusinessRegistrationNumber" $config.BusinessRegistrationNumber
Add-FormField $form "BusinessRegistrationAuthority" $config.BusinessRegistrationAuthority
Add-FormField $form "BusinessRegistrationCountry" $config.BusinessRegistrationCountry
Add-FormField $form "PrivacyPolicyUrl" $config.PrivacyPolicyUrl
foreach ($k in $config.OptInKeywords) { Add-FormField $form "OptInKeywords" $k }
$body = $form -join "&"

# ---- Build auth header ----
$pair = "$AccountSid`:$AuthToken"
$encodedCreds = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))

$headers = @{
    Authorization = "Basic $encodedCreds"
}

# ---- Send request ----
$response = Invoke-RestMethod `
    -Uri $uri `
    -Method Post `
    -Headers $headers `
    -Body $body `
    -ContentType "application/x-www-form-urlencoded"

# ---- Output result ----
Write-Host "TFV Request Submitted"
Write-Host "SID:" $response.sid
Write-Host "Status:" $response.status
Write-Host "Created:" $response.date_created
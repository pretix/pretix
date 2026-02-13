/*global $,u2f */

function b64enc(buf) {
    return base64js.fromByteArray(buf)
                   .replace(/\+/g, "-")
                   .replace(/\//g, "_")
                   .replace(/=/g, "");
}

function b64RawEnc(buf) {
    return base64js.fromByteArray(buf)
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function hexEncode(buf) {
    return Array.from(buf)
                .map(function(x) {
                    return ("0" + x.toString(16)).substr(-2);
				})
                .join("");
}

async function fetch_json(url, options) {
    const response = await fetch(url, options);
    const body = await response.json();
    if (body.fail)
        throw body.fail;
    return body;
}

/**
 * Transforms items in the credentialCreateOptions generated on the server
 * into byte arrays expected by the navigator.credentials.create() call
 * @param {Object} credentialCreateOptionsFromServer
 */
const transformCredentialCreateOptions = function (credentialCreateOptionsFromServer) {
    let {challenge, user, excludeCredentials} = credentialCreateOptionsFromServer;
    user.id = user.id.replace(/\_/g, "/").replace(/\-/g, "+");
    user.id = Uint8Array.from(atob(user.id), c => c.charCodeAt(0));

    challenge = challenge.replace(/\_/g, "/").replace(/\-/g, "+");
    challenge = Uint8Array.from(atob(challenge), c => c.charCodeAt(0));

    excludeCredentials = excludeCredentials.map(credentialDescriptor => {
        let {id} = credentialDescriptor;
        id = id.replace(/\_/g, "/").replace(/\-/g, "+");
        id = Uint8Array.from(atob(id), c => c.charCodeAt(0));
        return Object.assign({}, credentialDescriptor, {id});
    });

    const transformedCredentialCreateOptions = Object.assign(
        {}, credentialCreateOptionsFromServer,
        {challenge, user, excludeCredentials});

    return transformedCredentialCreateOptions;
};


/**
 * Transforms the binary data in the credential into base64 strings
 * for posting to the server.
 * @param {PublicKeyCredential} newAssertion
 */
const transformNewAssertionForServer = (newAssertion) => {
    const attObj = new Uint8Array(newAssertion.response.attestationObject);
    const clientDataJSON = new Uint8Array(newAssertion.response.clientDataJSON);
    const rawId = new Uint8Array(newAssertion.rawId);
    const transports = newAssertion.response.getTransports();
    const authenticatorAttachment = newAssertion.authenticatorAttachment;

    const registrationClientExtensions = newAssertion.getClientExtensionResults();

    return {
        id: newAssertion.id,
        rawId: b64enc(rawId),
        response: {
            attestationObject: b64enc(attObj),
            clientDataJSON: b64enc(clientDataJSON),
            transports: transports,
        },
        type: newAssertion.type,
        clientExtensionResults: JSON.stringify(registrationClientExtensions),
        authenticatorAttachment: authenticatorAttachment,
    };
};


const transformCredentialRequestOptions = (credentialRequestOptionsFromServer) => {
    let {challenge, allowCredentials} = credentialRequestOptionsFromServer;

    challenge = challenge.replace(/\_/g, "/").replace(/\-/g, "+");
    challenge = Uint8Array.from(atob(challenge), c => c.charCodeAt(0));

    allowCredentials = allowCredentials.map(credentialDescriptor => {
        let {id} = credentialDescriptor;
        id = id.replace(/\_/g, "/").replace(/\-/g, "+");
        id = Uint8Array.from(atob(id), c => c.charCodeAt(0));
        return Object.assign({}, credentialDescriptor, {id});
    });

    const transformedCredentialRequestOptions = Object.assign(
        {},
        credentialRequestOptionsFromServer,
        {challenge, allowCredentials});

    return transformedCredentialRequestOptions;
};

/**
 * Encodes the binary data in the assertion into strings for posting to the server.
 * @param {PublicKeyCredential} newAssertion
 */
const transformAssertionForServer = (newAssertion) => {
    const authData = new Uint8Array(newAssertion.response.authenticatorData);
    const clientDataJSON = new Uint8Array(newAssertion.response.clientDataJSON);
    const rawId = new Uint8Array(newAssertion.rawId);
    const sig = new Uint8Array(newAssertion.response.signature);
    const userHandle = new Uint8Array(newAssertion.response.userHandle);
    const assertionClientExtensions = newAssertion.getClientExtensionResults();
    const authenticatorAttachment = newAssertion.authenticatorAttachment;

    return {
        id: newAssertion.id,
        rawId: b64enc(rawId),
        type: newAssertion.type,
        response: {
            authenticatorData: b64RawEnc(authData),
            clientDataJSON: b64RawEnc(clientDataJSON),
            signature: b64RawEnc(sig),
            userHandle: b64RawEnc(userHandle),
        },
        authenticatorAttachment: authenticatorAttachment,
        clientExtensionResults: JSON.stringify(assertionClientExtensions)
    };
};

const startRegister = async (e) => {
    const publicKeyCredentialCreateOptions = transformCredentialCreateOptions(JSON.parse($("#webauthn-enroll").text()));

    // request the authenticator(s) to create a new credential keypair.
    let credential;
    try {
        credential = await navigator.credentials.create({
            publicKey: publicKeyCredentialCreateOptions
        });
    } catch (err) {
        $("#webauthn-error").removeClass("hidden");
        return console.error("Error creating credential:", err);
    }

    // we now have a new credential! We now need to encode the byte arrays
    // in the credential into strings, for posting to our server.
    const newAssertionForServer = transformNewAssertionForServer(credential);

    $("#webauthn-response").val(JSON.stringify(newAssertionForServer));
    $("#webauthn-form").submit();
};


const startLogin = async (e) => {
    const transformedCredentialRequestOptions = transformCredentialRequestOptions(JSON.parse($("#webauthn-login").text()));
    console.log(transformedCredentialRequestOptions);

    // request the authenticator to create an assertion signature using the
    // credential private key
    let assertion;
    try {
        assertion = await navigator.credentials.get({
            publicKey: transformedCredentialRequestOptions,
        });
    } catch (err) {
        $("#webauthn-error").removeClass("hidden");
        return console.error("Error when creating credential:", err);
    }

    // we now have an authentication assertion! encode the byte arrays contained
    // in the assertion data as strings for posting to the server
    const transformedAssertionForServer = transformAssertionForServer(assertion);

    // post the assertion to the server for verification.
    $("input, select, textarea").prop("required", false);
    $("#webauthn-response, #id_password").val(JSON.stringify(transformedAssertionForServer));
    $("#webauthn-form").submit();
};

$(function () {
    $("#webauthn-progress").hide();
    if ($("#webauthn-enroll").length) {
        $("#webauthn-progress").show();
        startRegister();
    } else if ($("#webauthn-login").length) {
        $("#webauthn-progress").show();
        startLogin();
    }
});

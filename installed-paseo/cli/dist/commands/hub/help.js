const resolutionHelp = "\nHub origin precedence: command origin/--hub, PASEO_HUB_URL, active stored login, then https://hub.paseo.sh.\nCredential precedence: --api-key, PASEO_HUB_API_KEY, then a stored login for the exact resolved origin.\n";
export function addHubResolutionHelp(command) {
    return command.addHelpText("after", resolutionHelp);
}
//# sourceMappingURL=help.js.map
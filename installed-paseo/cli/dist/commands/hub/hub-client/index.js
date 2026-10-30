import { HubCommandError } from "../error.js";
import { authorizationPollSchema, authorizationSchema, configurationResourcesSchema, enrollmentTokenSchema, installResponseSchema, projectsResponseSchema, triggersResponseSchema, triggerInstallationResponseSchema, triggerValidationResponseSchema, validationResponseSchema, } from "./internal/contracts.js";
import { requestHub } from "./internal/transport.js";
export class HubHttpClient {
    startCliAuthorization(origin) {
        return requestHub({
            origin,
            path: "/api/v1/cli-authorizations",
            method: "POST",
            body: {},
            successStatus: 201,
            schema: authorizationSchema,
            failureMessage: "Hub CLI login could not be started",
        });
    }
    async pollCliAuthorization(origin, deviceCode, timeoutMilliseconds) {
        try {
            return await requestHub({
                origin,
                path: "/api/v1/cli-authorizations/poll",
                method: "POST",
                body: { deviceCode },
                successStatus: 200,
                schema: authorizationPollSchema,
                timeoutMilliseconds,
                failureMessage: "Hub CLI login polling failed",
            });
        }
        catch (error) {
            if (error instanceof HubCommandError && error.code === "HUB_NETWORK_ERROR") {
                return { status: "retry_later" };
            }
            throw error;
        }
    }
    async listProjects(origin, apiKey) {
        const response = await requestHub({
            origin,
            path: "/api/v1/projects",
            method: "GET",
            apiKey,
            successStatus: 200,
            schema: projectsResponseSchema,
            failureMessage: "Hub project listing failed",
        });
        return response.projects;
    }
    async listTriggers(origin, apiKey) {
        const response = await requestHub({
            origin,
            path: "/api/v1/triggers",
            method: "GET",
            apiKey,
            successStatus: 200,
            schema: triggersResponseSchema,
            failureMessage: "Hub trigger export failed",
        });
        return response.triggers;
    }
    validateTrigger(origin, apiKey, yaml) {
        return requestHub({
            origin,
            path: "/api/v1/triggers/validate",
            method: "POST",
            apiKey,
            body: { yaml },
            successStatus: 200,
            schema: triggerValidationResponseSchema,
            failureMessage: "Hub trigger validation failed",
        });
    }
    installTrigger(origin, apiKey, yaml) {
        return requestHub({
            origin,
            path: "/api/v1/triggers/install",
            method: "POST",
            apiKey,
            body: { yaml },
            successStatus: 201,
            schema: triggerInstallationResponseSchema,
            failureMessage: "Hub trigger deployment failed",
        });
    }
    listConfigurationResources(origin, apiKey) {
        return requestHub({
            origin,
            path: "/api/v1/configuration-resources",
            method: "GET",
            apiKey,
            successStatus: 200,
            schema: configurationResourcesSchema,
            failureMessage: "Hub configuration resource listing failed",
        });
    }
    installConfiguration(input) {
        return requestHub({
            origin: input.origin,
            path: "/api/v1/configurations/install",
            method: "POST",
            apiKey: input.apiKey,
            body: configurationBody(input),
            successStatus: 201,
            schema: installResponseSchema,
            failureMessage: "Hub deployment failed",
        });
    }
    validateConfiguration(input) {
        return requestHub({
            origin: input.origin,
            path: "/api/v1/configurations/validate",
            method: "POST",
            apiKey: input.apiKey,
            body: configurationBody(input),
            successStatus: 200,
            schema: validationResponseSchema,
            failureMessage: "Hub configuration validation failed",
        });
    }
    async issueEnrollmentToken(origin, apiKey) {
        const response = await requestHub({
            origin,
            path: "/api/v1/daemons/enrollment-tokens",
            method: "POST",
            apiKey,
            successStatus: 201,
            schema: enrollmentTokenSchema,
            failureMessage: "Hub daemon enrollment authorization failed",
        });
        return response.token;
    }
}
function configurationBody(input) {
    return { projectSlug: input.projectSlug, files: input.files };
}
//# sourceMappingURL=index.js.map
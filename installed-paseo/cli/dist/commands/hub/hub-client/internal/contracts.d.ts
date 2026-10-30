import { z } from "zod";
export declare const authorizationSchema: z.ZodObject<{
    deviceCode: z.ZodString;
    userCode: z.ZodString;
    verificationUri: z.ZodURL;
    verificationUriComplete: z.ZodURL;
    expiresAt: z.ZodString;
    interval: z.ZodNumber;
}, z.core.$strict>;
export declare const authorizationPollSchema: z.ZodDiscriminatedUnion<[z.ZodObject<{
    status: z.ZodLiteral<"pending">;
    interval: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"slow_down">;
    interval: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"authorized">;
    interval: z.ZodNumber;
    credential: z.ZodString;
    organizationId: z.ZodString;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"denied">;
    interval: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"expired">;
    interval: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"disclosed">;
    interval: z.ZodNumber;
}, z.core.$strict>, z.ZodObject<{
    status: z.ZodLiteral<"retry_later">;
}, z.core.$strict>], "status">;
declare const projectSchema: z.ZodObject<{
    id: z.ZodString;
    slug: z.ZodString;
    name: z.ZodString;
}, z.core.$strict>;
export declare const projectsResponseSchema: z.ZodObject<{
    projects: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        slug: z.ZodString;
        name: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
declare const triggerSchema: z.ZodObject<{
    id: z.ZodString;
    name: z.ZodString;
    enabled: z.ZodBoolean;
    format: z.ZodEnum<{
        single_run: "single_run";
        legacy_multistep: "legacy_multistep";
    }>;
    yaml: z.ZodString;
}, z.core.$strict>;
export declare const triggersResponseSchema: z.ZodObject<{
    triggers: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        name: z.ZodString;
        enabled: z.ZodBoolean;
        format: z.ZodEnum<{
            single_run: "single_run";
            legacy_multistep: "legacy_multistep";
        }>;
        yaml: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const triggerValidationResponseSchema: z.ZodObject<{
    name: z.ZodString;
    valid: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const triggerInstallationResponseSchema: z.ZodObject<{
    triggerId: z.ZodString;
    name: z.ZodString;
    revisionId: z.ZodString;
    version: z.ZodNumber;
    active: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const configurationResourcesSchema: z.ZodObject<{
    daemons: z.ZodArray<z.ZodObject<{
        id: z.ZodString;
        slug: z.ZodString;
    }, z.core.$strict>>;
    github: z.ZodArray<z.ZodObject<{
        slug: z.ZodString;
        accountLogin: z.ZodString;
        accountType: z.ZodString;
        repositories: z.ZodArray<z.ZodString>;
    }, z.core.$strict>>;
    discord: z.ZodArray<z.ZodObject<{
        slug: z.ZodString;
        guildName: z.ZodString;
    }, z.core.$strict>>;
    slack: z.ZodArray<z.ZodObject<{
        slug: z.ZodString;
        teamName: z.ZodString;
    }, z.core.$strict>>;
    linear: z.ZodArray<z.ZodObject<{
        slug: z.ZodString;
        organizationName: z.ZodString;
    }, z.core.$strict>>;
}, z.core.$strict>;
export declare const installResponseSchema: z.ZodObject<{
    projectSlug: z.ZodString;
    version: z.ZodNumber;
    versionId: z.ZodString;
    active: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const validationResponseSchema: z.ZodObject<{
    projectSlug: z.ZodString;
    valid: z.ZodLiteral<true>;
}, z.core.$strict>;
export declare const enrollmentTokenSchema: z.ZodObject<{
    token: z.ZodString;
    expiresAt: z.ZodString;
}, z.core.$strict>;
export type CliAuthorization = z.infer<typeof authorizationSchema>;
export type CliAuthorizationPoll = z.infer<typeof authorizationPollSchema>;
export type HubProject = z.infer<typeof projectSchema>;
export type HubTrigger = z.infer<typeof triggerSchema>;
export type HubTriggerValidationResult = z.infer<typeof triggerValidationResponseSchema>;
export type HubTriggerInstallationResult = z.infer<typeof triggerInstallationResponseSchema>;
export type HubConfigurationResources = z.infer<typeof configurationResourcesSchema>;
export type HubInstallResult = z.infer<typeof installResponseSchema>;
export type HubValidationResult = z.infer<typeof validationResponseSchema>;
export {};
//# sourceMappingURL=contracts.d.ts.map
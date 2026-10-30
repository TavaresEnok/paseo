export function availableStarterTriggerConnections(resources, githubRepository) {
    return [
        ...resources.github.flatMap((connection) => githubRepository !== undefined && connection.repositories.includes(githubRepository)
            ? [
                {
                    id: `github:${githubRepository}`,
                    label: `GitHub — ${githubRepository}`,
                    provider: "github",
                    filters: {
                        connection: connection.slug,
                        repo: githubRepository,
                    },
                },
            ]
            : []),
        ...resources.slack.map(({ slug, teamName }) => ({
            id: `slack:${slug}`,
            label: `Slack — ${teamName}`,
            provider: "slack",
            filters: { connection: slug },
        })),
        ...resources.discord.map(({ slug, guildName }) => ({
            id: `discord:${slug}`,
            label: `Discord — ${guildName}`,
            provider: "discord",
            filters: { connection: slug },
        })),
    ];
}
//# sourceMappingURL=starter-trigger.js.map
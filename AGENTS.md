# Orientação para revisão desta cópia

Leia `README.md`, `docs/ARQUITETURA.md` e `docs/REVISAO.md` antes de alterar a implementação.

Este checkout é o snapshot para revisão da instalação NexoISP. Os arquivos preservam caminhos absolutos de produção; não execute serviços, scripts de instalação ou recuperação contra esses caminhos durante uma revisão. Trabalhe com fixtures e diretórios/bancos temporários. A publicação do código não autoriza retomar planos pausados.

Use `config/model-limits.json` como referência da política atual. Perfis, scripts antigos e fixtures podem conter informações históricas. Preserve a separação entre contas, papéis e sessões; qualquer mudança na política deve seguir o pedido explícito do usuário.

Ao sugerir correções, explique o cenário, a causa, o arquivo afetado e uma verificação proporcional. Não considere esta cópia um backup dos chats, dos tokens ou dos dados dos projetos.

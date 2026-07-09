"""
Template para criar uma nova fonte.

COMO USAR:
1. Copie este arquivo e renomeie para o nome do seu site (ex: meusite.py)
2. Altere o nome da classe e os metadados
3. Implemente ao menos get_last_episodes()
4. Pronto! A fonte será descoberta automaticamente na próxima inicialização.

Se o health-check falhar (site offline), a fonte aparece como [OFFLINE]
no gerenciador de fontes e não é usada até ficar disponível.

PLAYBACK:
- Implemente get_play_context() com url + referer/origin da *sua* fonte.
- O player não conhece CDNs de sites; tudo de anti-leech fica aqui.
"""

from app.domain import Anime, Episode, PlayContext
from app.infrastructure.sources._base import AnimeSource
from app.infrastructure.sources._utils import HEADERS, validate_response, get_episode_number


class MeuSite(AnimeSource):
    # ── Metadados ──────────────────────────────────────────
    name = "MeuSite"              # Nome exibido na interface
    identifier = "meusite"        # slug único (sem espaços)
    base_url = "https://meusite.com"  # URL para health-check automático
    color = ""                    # Cor da badge (ex: "#e67e22"). Vazio = gerada automaticamente.

    has_search = True              # O site tem busca?
    has_details = True             # O site tem página de detalhes?

    # ── Obrigatório: listar últimos episódios ──────────────
    def get_last_episodes(self) -> list[Episode]:
        ...
        # Exemplo:
        # import requests
        # from bs4 import BeautifulSoup
        # response = requests.get(self.base_url, headers=HEADERS)
        # if not validate_response(response):
        #     return []
        # soup = BeautifulSoup(response.text, self.default_analyzer)
        # episodes = []
        # for article in soup.find_all('article'):
        #     episodes.append(Episode(
        #         number='1',
        #         title=...,
        #         link=...,
        #         video_src='',
        #         image=...,
        #     ))
        # return episodes

    # ── Opcional: busca ────────────────────────────────────
    def search_by(self, name: str) -> list[Anime]:
        return []  # deixe vazio se o site não tiver busca

    # ── Opcional: detalhes do anime ────────────────────────
    def get_anime_details(self, link: str) -> Anime:
        return Anime(title='', rating='', link=link)

    # ── Playback (fonte é dona do referer/CDN) ─────────────
    def get_play_context(self, episode_link: str) -> PlayContext:
        # Stream direto:
        # return PlayContext(
        #     url="https://cdn…/video.mp4",
        #     referer=f"{self.base_url}/",
        #     origin=self.base_url,
        #     is_direct=True,
        #     page_url=episode_link,
        # )
        # Página (browser fallback):
        return PlayContext.page(episode_link, referer=f"{self.base_url}/")

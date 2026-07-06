from app.application import AnimeService
from app.infrastructure import AnimesOnlineFeedReader

def main():
    animes_online = AnimesOnlineFeedReader()
    service = AnimeService(animes_online)
    episodes = service.get_last_episodes()

    print(episodes)


if __name__ == "__main__":
    main()

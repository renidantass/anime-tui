from app.application import AnimeService
from app.infrastructure import AnimesOnlineFeedReader

def main():
    animes_online = AnimesOnlineFeedReader()
    service = AnimeService(animes_online)
    episodes = service.search_by("Naruto")

    print(episodes)


if __name__ == "__main__":
    main()

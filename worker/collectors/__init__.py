from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail
from .mercadolibre import MercadoLibreScraper
from .facebook import FacebookMarketplaceScraper
from .v6 import V6Scraper
from .kavak import KavakScraper
from .autocosmos import AutoCosmosScraper
from .mardelusados import MardelUsadosScraper
from .rosariogarage import RosarioGarageScraper
from .usadossantafe import UsadosSantaFeScraper
from .instagram import OnlyCarsUsadosScraper, SCClasificadosScraper
from .autocity import AutocityScraper
from .carone import CarOneScraper
from .gruporandazzo import GrupoRandazzoScraper

REGISTRY = {
    "mercadolibre": MercadoLibreScraper,
    "facebook":     FacebookMarketplaceScraper,
    "v6":           V6Scraper,
    "kavak":        KavakScraper,
    "autocosmos":   AutoCosmosScraper,
    "mardelusados": MardelUsadosScraper,
    "rosariogarage": RosarioGarageScraper,
    "usadossantafe": UsadosSantaFeScraper,
    "onlycarsusados": OnlyCarsUsadosScraper,
    "sc_clasificados": SCClasificadosScraper,
    "autocity": AutocityScraper,
    "carone": CarOneScraper,
    "gruporandazzo": GrupoRandazzoScraper,
}

__all__ = ["BaseScraper", "CollectorBlocked", "Listing", "ListingDetail", "REGISTRY"]

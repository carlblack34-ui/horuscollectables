# Guided TCG catalogue

The stock builder is Game → Era / Series → Set → Product, with separate language and stock-type choices. Pokémon's starter list is the supplied English set catalogue grouped into 13 eras. Sun & Moon's base expansion is displayed as **Sun & Moon Base**; its stored set name remains `Sun & Moon` to preserve compatibility.

20 games are offered as buttons. Starter set lists are supplied for Pokémon, Magic, Yu-Gi-Oh!, One Piece, Lorcana, Digimon, Dragon Ball Super (Fusion World), Flesh and Blood, Star Wars: Unlimited, Naruto and My Little Pony. Other games can be populated through **Manage catalogue**. Any additional game, era or set can be added and is stored in the database. These are starter lists, not exhaustive worldwide release catalogues or live product feeds. No regional completeness or current release status is implied. For games without formal eras, use a useful grouping such as “Main boosters”.

Naruto includes Kayou's English Smriti Heaven/Jin Scroll and Earth Scroll series, Ninja Age, and the 28 classic Bandai booster sets. My Little Pony includes Kayou's English Friendship Eternal Moon/Rainbow/Fun Moments/Star series, Kayou's playable TCG releases, and Enterplay CCG expansions and special releases. Publisher/line labels in the era picker keep these distinct. Chinese tier/wave catalogues and regional exclusives are not exhaustively seeded: add the exact packaging name through Manage catalogue. Older Bandai/Enterplay names are cross-checked against collector archives because their original publisher catalogues are no longer complete online. Existing catalogue entries and stock are preserved on upgrade.

Sealed product suggestions change with the game. Stock-type buttons switch to singles, graded cards and accessories, with corresponding product and condition dropdowns. Existing custom categories and conditions remain selectable when editing. Item names are generated from set and product selections until you edit the name yourself. Shared cost rules remain unchanged.

The schema adds `tcg`, `era`, `language` and a persistent catalogue without removing existing columns or records. Recognised original Pokémon set names receive a game and era automatically. Unrecognised historical set names are preserved; classify them when next editing the lot. Catalogue customisations are included in the PostgreSQL importer.

Starter references used to check names and formats:

- [Pokémon Sun & Moon base checklist](https://assets.pokemon.com/assets/cms2/pdf/trading-card-game/checklist/sm1_web_cardlist_en.pdf) and [Sun & Moon ETB](https://www.pokemon.com/us/pokemon-tcg/product-gallery/sun-moon-elite-trainer-box)
- [Magic product guide](https://www.magic.wizards.com/en/product-guide), [Innistrad: Midnight Hunt](https://magic.wizards.com/en/products/midnight-hunt), [The Brothers’ War](https://magic.wizards.com/en/products/the-brothers-war)
- [Yu-Gi-Oh! products](https://www.yugioh-card.com/en/products/) and [Metal Raiders](https://www.yugioh-card.com/eu/es/product/metal-raiders/)
- [One Piece Romance Dawn](https://en.onepiece-cardgame.com/products/boosters/op01.php), [Paramount War](https://en.onepiece-cardgame.com/products/boosters/op02.php), [Pillars of Strength](https://en.onepiece-cardgame.com/products/boosters/op03.php)
- [Disney Lorcana chapters and products](https://www.disneylorcana.com/en-GB/story/)
- [Digimon New Evolution](https://en.digimoncard.com/products/pack/ver1.php) and [Ultimate Power](https://en.digimoncard.com/cardlist/?category=508002&search=true)
- [Dragon Ball Super Fusion World products](https://www.dbs-cardgame.com/fw/asia-th/products/?page=2&tags=BoosterPack)
- [Flesh and Blood product releases](https://legacy.fabtcg.com/en/products/)
- [Star Wars: Unlimited first-year sets](https://starwarsunlimited.com/articles/behind-unlimited-lessons-accomplishments-2024)
- [Kayou My Little Pony collections](https://www.kayouofficial.com/en-US/ip-collections?ipId=ip-v6aaw7y3), [Naruto Heaven Scroll](https://www.kayouofficial.com/en-US/series/series-5zdty4vj), [Chapter Jin 2](https://www.kayouofficial.com/en-US/series/series-jj9iw6u0), [Chapter Jin 3](https://www.kayouofficial.com/en-US/series/series-cv8e3pgi), [Earth Scroll 1](https://www.kayouofficial.com/en-US/series/series-ldbindyv), [Earth Scroll 2](https://www.kayouofficial.com/en-US/series/series-8idoe481), [Ninja Age](https://www.kayouofficial.com/en-US/series/series-0nyket49)
- [Classic Naruto set archive](https://vintagenaruto.com/collection/naruto-ccg-main), [My Little Pony CCG archive](https://data.mlpmerch.com/ccg/) and [Enterplay official card reference](https://enter-play.com/mlpccgocr/mlpccg_ocr_v2.pdf)

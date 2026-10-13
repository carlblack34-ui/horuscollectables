"""Starter catalogue plus saved user additions; never claims every regional SKU."""
import ast
import re
from pathlib import Path

GAMES = ['Pokémon','Magic: The Gathering','Yu-Gi-Oh!','One Piece','Disney Lorcana','Digimon','Dragon Ball Super','Flesh and Blood','Union Arena','Weiss Schwarz','Star Wars: Unlimited','Cardfight!! Vanguard','Battle Spirits Saga','Final Fantasy','Force of Will','Altered','Riftbound','Other TCG']
PRODUCTS = {
 'sealed': ['Booster Box','Booster Pack','Elite Trainer Box (ETB)','Booster Bundle','Sleeved Booster','3-Pack Blister','Collection Box','Premium Collection','Tin','Mini Tin','Build & Battle Box','Build & Battle Stadium','Starter Deck','Theme Deck','Structure Deck','Commander Deck','Gift Bundle','Display Case','Other Sealed Product'],
 'singles':['Single Card','Promo Card','Bulk Cards','Energy / Resource Card','Playset'],
 'graded':['Graded Card','Graded Pack'],
 'accessories':['Sleeves','Toploaders','Binder','Deck Box','Playmat','Storage Box','Card Stand','Other Accessory']}
GAMES[GAMES.index('Other TCG'):GAMES.index('Other TCG')] = ['Naruto','My Little Pony']

# Starter entries checked against publishers. Series labels are portal groupings.
OTHER_SETS = {
 'One Piece': {'Main boosters':['OP-01 · Romance Dawn','OP-02 · Paramount War','OP-03 · Pillars of Strength']},
 'Disney Lorcana': {'Chapters & expansions':['The First Chapter','Rise of the Floodborn','Into the Inklands',"Ursula's Return",'Shimmering Skies','Azurite Sea',"Archazia's Island",'Reign of Jafar','Fabled','Whispers in the Well','Winterspell','Wilds Unknown']},
 'Magic: The Gathering': {'Expansions':['Innistrad: Midnight Hunt',"The Brothers' War",'Innistrad Remastered']},
 'Yu-Gi-Oh!': {'Classic boosters':['Metal Raiders']},
 'Digimon': {'Main boosters':['BT-01 · New Evolution','BT-02 · Ultimate Power']},
 'Dragon Ball Super': {'Fusion World':['FB01 · Awakened Pulse','FB02 · Blazing Aura','FB03 · Raging Roar']},
 'Flesh and Blood': {'Core expansions':['Welcome to Rathe','Arcane Rising','Monarch']},
 'Star Wars: Unlimited': {'Main expansions':['Spark of Rebellion','Shadows of the Galaxy','Twilight of the Republic']}}

GAME_PRODUCTS = {
 'Naruto':['Booster Box','Booster Pack','Blister Pack','Starter Deck','Collector Box','Premium Collector Box','Tin','Display Case','Other Sealed Product'],
 'My Little Pony':['Booster Box','Booster Pack','Starter Deck','Theme Deck','Two-Player Starter Set','Collector Box','Deluxe Set','Tin','Display Case','Other Sealed Product'],
 'Pokémon': PRODUCTS['sealed'],
 'Magic: The Gathering':['Play Booster Box','Play Booster Pack','Collector Booster Box','Collector Booster Pack','Draft Booster Box','Draft Booster Pack','Set Booster Box','Set Booster Pack','Commander Deck','Bundle','Gift Bundle','Starter Kit','Booster Box','Booster Pack','Display Case','Other Sealed Product'],
 'Yu-Gi-Oh!':['Booster Box','Booster Pack','Structure Deck','Starter Deck','Tin','Legendary Collection','Speed Duel Box','Display Case','Other Sealed Product'],
 'One Piece':['Booster Box','Booster Pack','Starter Deck','Double Pack','Premium Collection','Gift Collection','Display Case','Other Sealed Product'],
 'Disney Lorcana':['Booster Box','Booster Pack','Starter Deck','Illumineer’s Trove','Gift Set','Gift Box','Gateway','Illumineer’s Quest','Display Case','Other Sealed Product']}

def seed_other(d):
    for game,eras in OTHER_SETS.items():
        for era,sets in eras.items():
            for name in sets:
                d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',(game,era,name))

def pokemon_catalog():
    source=(Path(__file__).parent/'pokemon_sets.py').read_text(encoding='utf-8').split('CATEGORY_OPTIONS')[0]
    eras={}
    for match in re.finditer(r'# ([^\n]+)\n(.*?)(?=\n\s*#|\n\])',source,re.S):
        era=match[1].strip().removesuffix(' Series')
        sets=[]
        for line in match[2].splitlines():
            line=line.strip().rstrip(',')
            if line.startswith('"'): sets.append(ast.literal_eval(line))
        eras[era]=sets
    return eras

def seed(d):
    for game in GAMES:
        d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',(game,'',''))
    for era,sets in pokemon_catalog().items():
        for name in sets:
            d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',('Pokémon',era,name))

def load(d):
    result={}
    for r in d.execute('SELECT game,era,set_name FROM catalogue ORDER BY id'):
        eras=result.setdefault(r['game'],{})
        if r['era']:
            sets=eras.setdefault(r['era'],[])
            if r['set_name'] and r['set_name'] not in sets: sets.append(r['set_name'])
    return result

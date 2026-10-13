"""Naruto and MLP: publisher-labelled series keep distinct card lines separate."""
ADDITIONS = {
 'Naruto': {
  'Kayou · Smriti · Heaven / Jin Scroll': ['Heaven Scroll Series 1','Chapter Jin Series 2','Chapter Jin Series 3'],
  'Kayou · Smriti · Earth Scroll': ['Earth Scroll Series 1','Earth Scroll Series 2'],
  'Kayou · Premium collections': ['Ninja Age'],
  'Bandai CCG · Naruto': ['The Path to Hokage','Coils of the Snake','Curse of the Sand','Revenge and Rebirth','Dream Legacy','Eternal Rivalry','Quest for Power','Battle of Destiny','The Chosen','Lineage of the Legends'],
  'Bandai CCG · Shippuden': ['Approaching Wind','A New Chronicle','Fateful Reunion','Emerging Alliance','Foretold Prophecy','Broken Promises','Will of Fire','Fangs of the Snake','Path of Pain','Tales of the Gallant Sage','Shattered Truths','Weapons of War','Invasion',"Sage's Legacy","Kage's Summit","Avenger's Wrath","Hero's Ascension",'Ultimate Ninja Storm 3']},
 'My Little Pony': {
  'Kayou · Friendship Eternal · Moon Edition': ['Moon Edition Series 1','Moon Edition Series 2','Moon Edition Series 3'],
  'Kayou · Friendship Eternal · Rainbow Edition': ['Rainbow Edition Series 1','Rainbow Edition Series 2'],
  'Kayou · Friendship Eternal · Fun Moments Edition': ['Fun Moments Edition Series 1','Fun Moments Edition Series 2','Fun Moments Edition Series 3'],
  'Kayou · Friendship Eternal · Star Edition': ['Star Edition Series 1'],
  'Kayou · Trading Card Game': ['Friendships Begin','Fantasy Wonderland','Discord!!!','Nightmare Night'],
  'Enterplay · Collectible Card Game': ['Premiere','Canterlot Nights','The Crystal Games','Absolute Discord','Equestrian Odysseys','High Magic','Marks in Time','Defenders of Equestria','Seaquestria and Beyond','Friends Forever'],
  'Enterplay · Special releases': ['Rock N Rave','Celestial Solstice','GenCon']}}

def seed(d):
    for game, eras in ADDITIONS.items():
        d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',(game,'',''))
        for era, sets in eras.items():
            for name in sets:
                d.execute('INSERT INTO catalogue(game,era,set_name) VALUES (?,?,?) ON CONFLICT DO NOTHING',(game,era,name))

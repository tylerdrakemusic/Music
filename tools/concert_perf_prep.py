from matplotlib.pyplot import cool
from torch import ne
from song_production import *
from quantum_rt import quuffle as coolShuffle
from colorama import Fore, Style, init
from pydub import AudioSegment
from datetime import datetime
from ty_py import song_utils

def tag_and_shuffle(songs):
    identifier = song_utils.generate_identifier(songs)
    return (identifier, coolShuffle(songs))

def tag_only(songs):
    identifier = song_utils.generate_identifier(songs)
    return(identifier,songs)

def prep_music_performance(currentSongs,build=True,play=True):
    # Banner to print (for demo purposes)
    banner = f"""
    {Fore.RED}{Style.BRIGHT}        _
        / `-._ 
        /  {Fore.YELLOW}.. {Fore.RED}`-._      {Fore.GREEN}Musical
        /  {Fore.YELLOW}/\\  {Fore.RED}`-._ 
    /  {Fore.YELLOW}/  \\  {Fore.RED}`-._    {Fore.GREEN}Banner
    /_/{Fore.YELLOW}/ __ \\ {Fore.RED}`-._ 
    / / {Fore.YELLOW}/\\__\\ \\ {Fore.RED}`-._ 
    / /{Fore.YELLOW}  /  /\\ \\_ _.-' 
    {Fore.YELLOW}\\   /  /\\ \\_ _.-' 
    {Fore.YELLOW}\\ /  /  \\/ _.-' 
    {Fore.YELLOW}\\  /  _.-' 
    {Fore.YELLOW}\\_ .-'{Style.RESET_ALL}
"""
    #Loop through the list of songs
    if(build):
        combined_audio = AudioSegment.empty()
    for song in currentSongs:

        if(play) :
            print(banner)
            print(Fore.LIGHTMAGENTA_EX + song.title + " by " + song.artist + Style.RESET_ALL)
            # Create a promotional plan for the song
            promotional_plan = PromotionalPlan(song)
            
            # Execute the promotional plan
            promotional_plan.execute()
        
        if(build):
            # Load the audio file
            audio = AudioSegment.from_file(song.audio_path)
            # Append to the combined audio
            combined_audio += audio

    if not os.path.exists(output_path):
        combined_audio.export(output_path, format='mp3')
        print(f"Combined audio saved to {output_path}")


output_directory = 'performancePrep'
if not os.path.exists(output_directory):
    os.makedirs(output_directory)
# Initialize an empty audio segment

starCrossed = Song('Star Crossed','Scary Kids, Scaring Kids','06 - Star Crossed.mp3')
comfortablyNumb = Song('Comfortably Numb','Pink Floyd', "06 Comfortably Numb.mp3")
whiteRoom = Song('White Room','Cream', "12 White Room.mp3")
wonderfulTonight = Song('Wonderful Tonight','Clapton', "04 Wonderful Tonight.mp3")
everSeenTheRain = Song('Ever Seen The Rain','Creedence Clearwater Revival', "05 Have You Ever Seen the Rain  (Mono Single).mp3")
californication = Song('Californication','Red Hot Chili Peppers', "06 Californication.mp3")
youReallyGotMe = Song('You Really Got Me','The Kinks', "03 You Really Got Me.mp3")

# Jim Mann / Echo Ty Originals
darkEyedLady = Song('Dark Eyed Lady','Jim Mann', "Dark Eyed Lady 2-27-79.mp3")
marigolds = Song('Marigolds','Echo Ty', "Master$1$Marigold_mastered.mp3")
dancingAndSinging = Song('Dancing and Singing','Jim Mann', "Dancing&Singing1-7-24.mp3")

#Anne Freeman April Recital
aprilRain = Song('April Rain','Delain', "01 April Rain.mp3")
cruelToBeKind = Song('Cruel To Be Kind','Nick Lowe', "01 Cruel to Be Kind.mp3")
fame = Song('Fame','Irene Cara', "01 Fame.mp3")
girlOnFire = Song('Girl On Fire','Alicia Keys', "01 Girl On Fire.mp3")
heartLikeATruck = Song('Heart Like A Truck','Lainey Wilson', "01 Heart Like a Truck.mp3")
hotStuff = Song('Hot Stuff','Donna Summer', "01 Hot Stuff.mp3")
myKindaParty = Song('My Kinda Party','Jason Aldean', "04 My Kinda Party.mp3")
never = Song('Never','Heart', "03 Never.mp3")
people = Song('People','Quantum Heart', "07 People.mp3")
songBird = Song('SongBird','Barbra Streisand', "10 Songbird.mp3")
sayYesToHeaven = Song('Say Yes To Heaven','Lana Del Ray', "01 Say Yes To Heaven.mp3")
separateWays = Song('Separate Ways','Journey', "09 Separate Ways (Worlds Apart) [2024 Remaster](1).mp3")
shesAllIWannaBe = Song('She\'s All I Wanna Be','Tate McRae', "01 she's all i wanna be.mp3")
stay = Song('Stay','Rhianna', "09 Stay (feat Mikky Ekko).mp3")
sugerAndSpice = Song('Suger And Spice','Jocelyn & Chris Arndt',"01 Sugar and Spice.mp3")
superStition = Song('Superstition','Stevie Wonder', "06 Superstition.mp3")
youMakeLovingFun = Song('You Make Loving Fun','Fleetwood Mac', "08 You Make Loving Fun.mp3")

#x
blueOnBlack = Song('Blue on Black', "Kenny Wayne Shephard", "03 Blue on Black.mp3")
wholeLottaLove = Song('Whole Lotta Love', "Led Zeppelin", "01 Whole Lotta Love.mp3")
rockyMountainWay = Song('Rocky Mountain Way', "Joe Walsh", "10 Rocky Mountain Way.mp3")
godzilla = Song('Godzilla', "Blue Oyster Cult", "01 Godzilla.mp3")
jaipeurdlavion = Song('J\'ai peur de l\'avion', "Stromae", "01 J'ai peur de l'avion.mp3")
freeBird = Song('Free Bird', "Lynyrd Skynyrd", "08 Free Bird.mp3")
whiteRabbit = Song('\'White Rabbit\'', "Jefferson Airplane", "10 White Rabbit.mp3")

#Flashjam March Rockstar

# Copper Creek PREP
jump = Song('Jump','Van Halen', "02 Jump.mp3", None)
heavychevy = Song('Heavy Chevy', 'Alabama Shakes', 'heavychevy_alabamaShakes.mp3', None)
livinonaprayer = Song("Livin' On a Prayer", 'Bon Jovi', "03 Livin' On a Prayer.mp3", None)
smokeonthewater = Song('Smoke On the Water', 'Deep Purple', '12 Smoke On the Water.mp3', None)
lifeinthefastlane = Song('Life In the Fast Lane', 'Eagles', '03 Life In the Fast Lane.mp3', None)
meandbobbymcgee = Song('Me and Bobby McGee', 'Janis Joplin', '12 Me and Bobby McGee.mp3', None)
dontstopbelievin2024remaster = Song("Don't Stop Believin' (2024 Remaster)", 'Journey', "02 Don't Stop Believin' (2024 Remaster).mp3", None)
carryonwaywardson = Song('Carry On Wayward Son', 'Kansas', '01 Carry On Wayward Son.mp3', None)
blackmagicwoman = Song('Black Magic Woman', 'Santana', '02 Black Magic Woman _ Gypsy Queen.m4a', None)
doitagain = Song('Do It Again', 'Steely Dan', '07 Do It Again.mp3', None)
toomuchtimeonmyhands = Song('Too Much Time On My Hands', 'Styx', '04 Too Much Time On My Hands.mp3', None)
loveshack = Song('Love Shack', "The B-52's", '04 Love Shack.mp3', None)
smoothfeatrobthomas = Song('Smooth (feat. Rob Thomas)', 'Santana', '03 Smooth (feat. Rob Thomas).mp3', None)
youresovain = Song("You're So Vain", 'Carly Simon', "03 You're So Vain.mp3", None)
iris = Song("Iris", 'Goo Goo Dolls', "11 Iris.m4a", None)
pretzilLogic = Song("Pretzil Logic", 'Steely Dan', "08 Pretzel Logic.m4a", None)
changeTheWorld = Song("Change The World", 'Eric Clapton', "01 Change the World.m4a", None)
stopDragginMyHeartAround = Song("Stop Draggin' My Heart Around",'Stevie Nicks','05 - Stop Draggin\' My Heart Around (with Tom Petty and The Heartbreakers).mp3')
loveSneakin = Song('Love Sneakin\' Up On You','Bonnie Raitt','08 - Love Sneakin\' Up On You.mp3' )
theLetter = Song('The Letter','Joe Cocker','06 - The Letter (Live At The Fillmore East).mp3')
moreThanAFeeling = Song('More Than a Feeling','Boston','01 - More Than a Feeling.mp3')
reelingInTheYears = Song('Reeling In The Years','Steely Dan','10 - Reeling In The Years.mp3')
radarLove = Song('Radar Love','Golden Earring','01 - Radar Love.mp3')
manIFeelLikeAWoman = Song('Man! I Feel Like A Woman!',"Shania Twain",'01 - Man! I Feel Like A Woman!.mp3')
rhiannon = Song('Rhiannon','Fleetwood Mac', '01 Rhiannon.m4a')
longTrainRunning = Song('Long Train Runnin\'','Doobie Brothers','02 - Long Train Runnin\' (2016 Remaster).mp3')
evilWays = Song('Evil Ways','Santana','07 - Evil Ways.mp3')
hypotheticals = Song('Hypotheticals','Lake Street Dive','01 - Hypotheticals.mp3')
aintItFun = Song('Ain\'t It Fun','Paramore','06 - Ain\'t It Fun.mp3')
rollWithTheChanges = Song('Roll With The Changes','REO Speewagon','01 - Roll With The Changes.mp3')
peg = Song('Peg','Steely Dan','08 - Peg.mp3')
goldOnTheCeiling = Song('Gold On The Ceiling', 'Black Keys', 'GoldOnTheCeiling_BlackKeys.mp3')
iWillSurvive = Song('I Will Survive', 'Gloria Gaynor', '11 - I Will Survive (Single Version).mp3')
blueOnBlackInC = Song('Blue On Black','Kenny Wayne Shepard', '03 Blue On Black_n_steps_5_c.wav')
naturalWoman = Song('A Natural Woman','Carole King','12 - (You Make Me Feel Like) A Natural Woman.mp3')
iFeelTheEarthMove = Song('I Feel the Earth Move','Carole King','01 - I Feel the Earth Move.mp3')
copperCreeknaturalWomanBb = Song('A Natural Woman','Carole King','12 - (You Make Me Feel Like) A Natural Woman_n_steps_1.wav')
copperCreekCallMeMinus3NSteps = Song('Call Me','Blondie','01 - Call Me_n_steps_-3.wav')
bakerStreet = Song('Baker Street','Gerry Rafferty','02 - Baker Street.mp3')
ladyMarmlade = Song('Lady Marmalade','Patti LaBelle','01 - Lady Marmalade.mp3')
discoInferno = Song('Disco Inferno','Tina Turner','03 - Disco Inferno.mp3')
logicalSong = Song('The Logical Song','Supertramp','02 - The Logical Song (Remastered 2010).mp3')
imAlright = Song('Im Alright','Kenny Loggins','07 - I\'m Alright (Theme from _Caddyshack_).mp3')
whatYouNeedBb = Song('What You Need Bb','INXS','02 - What You Need (Single)_n_steps_-1.wav')
whatYouNeed = Song('What You Need','INXS','02 - What You Need (Single).mp3')
pickUpThePieces = Song('Pick Up the Pieces','Average White Band','03 - Pick Up the Pieces.mp3')
tequila = Song('Tequila','The Champs','01 - Tequila.mp3')
flyAway = Song('Fly Away','Tyler James Drake','Master 4 Fly Away.mp3')
shadedJade = Song('Shaded Jade','Tammala Cameron,','Deeper Shade of Jade T&G.mp3')
onTheDarkSide = Song('On The Dark Side','John Cafferty & The Beaver Brown Band','01 - On The Darkside.mp3')
heartOfRockAndRoll = Song('Heart of Rock and Roll','Huey Lewis & The News','01 - The Heart Of Rock And Roll.mp3')
whatILikeAboutYou = Song('What I Like About You','The Romantics','01 - What I Like About You (Album Version).mp3')


#June FLashMan
thrillIsGone = Song('Thrill Is Gone', 'BB King', '09 The Thrill Is Gone.mp3', None)
touchOfGrey = Song('Touch of Grey', 'Grateful Dead', '01 Touch of Grey.mp3', None)
slide = Song('Slide', 'Goo Goo Dolls', '02 Slide.mp3', None)
rockyMountainWay = Song('Rocky Mountain Way', 'Joe Walsh', '10 Rocky Mountain Way.m4a', None)
breakDown = Song('Breakdown', 'Tom Petty', '1-09 Breakdown.m4a' )

#Sept TrueFlashChamps
carnival = Song('Carnival', 'Natalie Merchant', '05 Carnival.mp3', None)
jacky = Song('Jacky',"Jim Mann",'Jacky1-7-24.mp3')
separateWays = Song('Separate Ways','Journey', "09 Separate Ways.mp3", None)
naturalWoman = Song('A Natural Woman', 'Arethra Franklin','07 - (You Make Me Feel Like) A Natural Woman.mp3',None)

#Feb 2025 Flashjam
Twentyfiveor6tofour = Song('25 Or 6 to 4','Chicago','02 - 25 or 6 to 4 (2002 Remaster).mp3')
bornToRun = Song('Born To Run','Bruce Springsteen','05 - Born To Run.mp3')
josie = Song('Josie','Steely Dan','07 - Josie.mp3')


#Anne Freeman May Recital
rhiannonInBm = Song('Rhiannon', 'Fleetwood Mac', '01 RhiannonInBm.wav')
meWithoutYou = Song('Me WIthout You','Floor Jansen','07 Me Without You.m4a')
everythingINeed = Song('Everything I Need', 'Skylar Grey',"01 - Everything I Need (Film Version).mp3")
barracuda = Song('Barracuda','Heart','01 - Barracuda.mp3')
furtherOnUpTheRoad=Song('Futhur On Up the Road', 'Joe Bonamassa and Eric Clapton', '07 - Further On Up the Road (Live)_n_steps_2.wav')
boysOfSummerInEm=Song('The Boys Of Summer','Don Henley','01 - The Boys Of Summer_n_steps_1.wav')
openArms=Song('Open Arms','Journey','12 - Open Arms.mp3')
mrBrightSide=Song('Mr. Brightside','The Killers','02 - Mr. Brightside.mp3')
rebelGirl=Song('Rebel Girl', 'Bikini Kill','04 - Rebel Girl [Explicit]_n_steps_-2.wav')
ourLipsAreSealed=Song('Our Lips Are Sealed','The Go-Go\'s','01 - Our Lips Are Sealed (2011 Remaster).mp3')
somewhere=Song('Somewhere','Barbra Streisand','cut_12 - Somewhere.mp3')
dangerousWoman=Song('Dangerous Woman','Ariana Grande','02 - Dangerous Woman.mp3')
goingToCalifornia=Song('Going to California','Amy Lee','03 - Going to California.mp3')
hitTheRoadJack=Song('Hit the Road Jack','Tokyo Ska Paradise Orchestra','11 - Hit the Road Jack_n_steps_6.wav')
callMe=Song('Call Me','Shinedown','11 - Call Me.mp3')
callMeBlondie=Song('Call Me', 'Blondie','01 - Call Me.mp3')

#Hyperthreat December Recital
lastChristmas = Song('Last Christmas','Wham!',"01 - Last Christmas.mp3")
dreams = Song('Dreams', 'Fleetwood Mac','01 - Last Christmas.mp3')
whiteChristmas = Song('White Christmas', 'Bing Crosby', '11 - White Christmas.mp3')
aintItfun = Song('Ain\'t It Fun','Paramore','06 - Ain\'t It Fun.mp3')
aintNoLoveInOklahoma = Song('Ain\'t No Love In Oklahoma', 'Luke Combs','01 - Ain\'t No Love In Oklahoma (From Twisters_ The Album).mp3')
theChain = Song('The Chain','Fleetwood Mac','(Disc 2) 01 - The Chain (2002 Remaster).mp3')
hurt = Song('Hurt','Christina Aguilera','(Disc 2) 06 - Hurt.mp3')
jolene = Song('Jolene','Dolly Parton','01 - Jolene.mp3')
iAmNotOkay = Song('I Am Not Okay', 'Jelly Role','04 - I Am Not Okay.mp3')

#Hyperthreat May Recital 2025
nineTo5 = Song('9 to 5','Dolly Parton','(Disc 2) 08 - 9 to 5_n_steps_-1.wav')
edgeof17 = Song('Edge of 17','Stevie Nicks','01 - Edge of Seventeen.mp3')
scarTissueinEm_transposed = Song('Scar Tissue','Red Hot Chili Peppers','03 - Scar Tissue_n_steps_4.wav')
iAmNotOkayinC_transposed = Song('I Am Not Okay', 'Jelly Role','04 - I Am Not Okay_n_steps_5.wav')
beWithoutYou_transposed = Song('Be With You','Mary J blije','04 - Be Without You (Kendu Mix) [Explicit]_n_steps_2.wav')
diamonds_transposed = Song('Diamonds','Rihanna','01 - Diamonds_n_steps_1.wav')
ticketToRide_transposed = Song('Ticket To Ride','The Beatles','07 - Ticket To Ride (Remastered 2009)_n_steps_3.5.wav')
weWerentForTheWind_transposed = Song('We Weren\'t For The Wind','Ella Langley','16 - weren\'t for the wind_n_steps_1.wav')
getBehiindMe = Song('Get Behind Me','Emerson Day','01 - Get Behind Me.mp3')
getBehindMeInAm_transposed = Song('Get Behind Me','Emerson Day','01 - Get Behind Me_n_steps_-2.wav')
stand = Song('Stand','Anne Wilson.','01 - Stand.mp3')
ashes = Song('Ashes','Celine Dion','15 - Ashes.mp3')
sayItAintSo = Song('Say It Ain\'t So','Weezer','07 - Say It Ain\'t So.mp3')
sayItAintSo_transposed_Em = Song('Say It Ain\'t So','Weezer','07 - Say It Ain\'t So_n_steps_4.wav')
outOfOklahoma = Song('Out Of Oklahoma','Lainey Wilson','01 - Out of Oklahoma (From Twisters_ The Album).mp3')
aintNoSunshine = Song('Ain\'t No Sunshine','Bill Withers','02 - Ain\'t No Sunshine.mp3')
""" hypSongs = [
      aprilRain, 
      cruelToBeKind,
      fame,
      girlOnFire,
      heartLikeATruck,
      hotStuff,
    myKindaParty,
     never,
     people,
     songBird,
     sayYesToHeaven,
     separateWays,
     shesAllIWannaBe,
     stay,
    sugerAndSpice,
     superStition,
     youMakeLovingFun
] """

#hyperThreat September 2025 Recital
#Anne
genieInABottle = Song('Genie In A Bottle','Christina Aguilera','01 - Genie In a Bottle.mp3')
#Tyler
flyAway = Song('Fly Away','Tyler James Drake','Fly Away_tuned vox_2_01.mp3')
#Olivia
handInMyPocket = Song('Hand In My Pocket','Alanis Morissette','04 - Hand in My Pocket [Explicit].mp3')
loveFool = Song('Lovefool','The Cardigans','07 - Lovefool.mp3')
fakePlasticTrees = Song('Fake Plastic Trees','Radiohead','04 - Fake Plastic Trees.mp3')
#Chloe
imagine = Song('Imagine','Eva Cassidy','05 - Imagine (Imagine).mp3')
think = Song('Think','Aretha Franklin','Aretha_Franklin_Think(Custom_Backing_Track-3).mp3')
riseUp = Song('Rise Up','Andra Day','11 - Rise Up.mp3')
#Isabelle
missedCall = Song('Missed Call','Treaty Oak','Treaty_Oak_Revival_Missed_Call(Custom_Backing_Track+4).mp3')
parachute = Song ('Parachute','Chris Stapleton','04 - Parachute.mp3')
undressed = Song('Undressed','Sombr','01 - undressed_n_steps_2.wav')
backToFriends = Song('Back To Friends','Sombr','sombr_back_to_friends(Custom_Backing_Track+1).mp3')

#Natane
diamondsSamSmith = Song('Diamonds','Sam Smith','02 - Diamonds.mp3')
laVidaEsFria = Song('La Vida Es Fría','Jason Joshua','07 - La Vida Es Fría.mp3')
creep = Song('Creep','Alba Reche','Creep Alba Reche.mp3')

#Dani Dubois
takeItEasyEagles = Song('Take It Easy','The Eagles','01 - Take It Easy (2013 Remaster).mp3')
goYourOwnWay = Song('Go Your Own Way','Fleetwood Mac','05 - Go Your Own Way (2004 Remaster).mp3')

#Tyler Drake
flyWay = Song('Fly Away','Tyler James Drake','Fly Away_rough bass drums_01.mp3')
whatIDo = Song('What I Do','Tyler James Drake','What i do Clean Master.mp3')

#Hyperthreat Recital September 2025
ϕSaturdaySeptember20ζ2025HyperThreatRecitalSong = [furtherOnUpTheRoad, genieInABottle, flyAway, handInMyPocket, loveFool, fakePlasticTrees, imagine, think, riseUp, missedCall, parachute, undressed, diamondsSamSmith, laVidaEsFria, creep, takeItEasyEagles, goYourOwnWay]


#2024
#Anne Freeman May Recital
ϕhypSongs = [people, rhiannonInBm, meWithoutYou, barracuda,everythingINeed,furtherOnUpTheRoad,boysOfSummerInEm,
            openArms,mrBrightSide,rebelGirl,ourLipsAreSealed,somewhere,dangerousWoman,goingToCalifornia,hitTheRoadJack,callMe]

ϕbeautifulHyperThreatRecitalSongs = [furtherOnUpTheRoad,meWithoutYou,people,callMe,mrBrightSide,boysOfSummerInEm,rhiannonInBm,ourLipsAreSealed,hitTheRoadJack,rebelGirl,somewhere,goingToCalifornia,dangerousWoman,openArms,everythingINeed,barracuda]
ϕholiday2024HyperThreatRecitalSongs = [lastChristmas,dreams,whiteChristmas,aintItfun,aintNoLoveInOklahoma,theChain,hurt,jolene,iAmNotOkay]


#Hyperthreat Recital 2025
ϕSaturdaymay3ζ2025HyperThreatRecitalSong = [nineTo5,edgeof17,scarTissueinEm_transposed,iAmNotOkayinC_transposed,beWithoutYou_transposed,diamonds_transposed,ticketToRide_transposed,weWerentForTheWind_transposed,imAlright,getBehindMeInAm_transposed,stand,ashes,sayItAintSo_transposed_Em, aintNoSunshine, outOfOklahoma, sugerAndSpice]



##Copper Creek
ftadlSongs = [jump,separateWays,heavychevy,livinonaprayer,smokeonthewater,lifeinthefastlane,meandbobbymcgee,dontstopbelievin2024remaster,carryonwaywardson,blackmagicwoman,doitagain,toomuchtimeonmyhands,loveshack,smoothfeatrobthomas,youresovain]
ftadlSongs713 = [smoothfeatrobthomas, youresovain, doitagain, dontstopbelievin2024remaster]
ftadls2024SeasonWinningSongs = [carnival,separateWays]
ftadlSunJuly28Rehearsal = [breakDown,blackmagicwoman,thrillIsGone,wonderfulTonight,changeTheWorld,pretzilLogic]
ftadlThurAug22Rehearsal = [jacky,rockyMountainWay,jump,stopDragginMyHeartAround,separateWays,heavychevy]
ftadlSepRehearsal = [theLetter,loveshack,loveSneakin,livinonaprayer,moreThanAFeeling, jump]
ftadl_Sep19_6pmRehearsal = [loveshack,theLetter,livinonaprayer,toomuchtimeonmyhands,callMeBlondie]
ftadl_Oct3_6pmRehearsal = [reelingInTheYears,radarLove,manIFeelLikeAWoman,carnival,rhiannon,livinonaprayer,dontstopbelievin2024remaster]
ftadl_Oct10_6pmRehearsal = [reelingInTheYears,livinonaprayer,dontstopbelievin2024remaster,heavychevy,wonderfulTonight,meandbobbymcgee,smoothfeatrobthomas,youresovain,doitagain,blackmagicwoman]
ftadl_Oct17_6pmRehearsal = [blackmagicwoman,smokeonthewater,pretzilLogic,changeTheWorld,theLetter,loveshack,loveSneakin,rockyMountainWay]
ftadl_Oct24_6pmRehearsal = [longTrainRunning,radarLove,rhiannon,toomuchtimeonmyhands,stopDragginMyHeartAround,reelingInTheYears]
ftadl_Nov7_6pmRehearsal = [loveSneakin,pretzilLogic,manIFeelLikeAWoman,carnival,wonderfulTonight,evilWays]
ftadl_Nov14_6pmRehearsal = [moreThanAFeeling,evilWays,youresovain,changeTheWorld,separateWays,thrillIsGone]
ftadl_Nov21_6pmRehearsalAndPrepForBirthdayPerformance = [separateWays,blackmagicwoman,reelingInTheYears,meandbobbymcgee,loveSneakin,loveshack,theLetter,youresovain,longTrainRunning]
ftadl_Jan13_6pmRehearsal = [hypotheticals,aintItFun,peg,theLetter,evilWays,reelingInTheYears,rhiannon]
ftadl_Jan16_6pmRehearsal = [peg,reelingInTheYears,changeTheWorld,breakDown,blackmagicwoman,evilWays]
ftadl_Jan27_6pmRehearsal = [hypotheticals,aintItFun,peg,theLetter,loveshack,rhiannon]
ftadl_Feb6_6pmRehearsal = [hypotheticals,aintItFun,peg,rollWithTheChanges,theLetter,loveshack,rhiannon]
ftadl_Feb20_6pmRehearsal = [hypotheticals,aintItFun,rhiannon,carnival,stopDragginMyHeartAround]
flashJam_Feb19 = [josie,bornToRun,Twentyfiveor6tofour]
copper_creek_feb25_2025 = [meandbobbymcgee,goldOnTheCeiling,loveSneakin,manIFeelLikeAWoman,reelingInTheYears,rhiannon,stopDragginMyHeartAround,toomuchtimeonmyhands,blueOnBlackInC,iWillSurvive]
copper_creek_march3_2025 = [blueOnBlack,toomuchtimeonmyhands,heavychevy,doitagain,wonderfulTonight,Twentyfiveor6tofour,iWillSurvive,callMeBlondie,naturalWoman]
copper_creek_march10_2025 = [heavychevy,iWillSurvive,iFeelTheEarthMove,rollWithTheChanges,copperCreekCallMeMinus3NSteps,copperCreeknaturalWomanBb,bakerStreet]
ↂmarch17ζ2025 = [heavychevy, iWillSurvive, iFeelTheEarthMove, bakerStreet, copperCreeknaturalWomanBb, loveshack, jacky]
ↂmarch24ζ2025 = [rollWithTheChanges,meandbobbymcgee,rhiannon,peg,ladyMarmlade,discoInferno]
ↂmarch31ζ2025 = [meandbobbymcgee,rhiannon,ladyMarmlade,discoInferno,aintItFun,blackmagicwoman]
ↂapril7ζ2025 = [logicalSong,blueOnBlackInC, manIFeelLikeAWoman,Twentyfiveor6tofour,discoInferno, goldOnTheCeiling,reelingInTheYears,breakDown]
ↂapri24ζ2025 = [aintItFun,doitagain,callMeBlondie,ladyMarmlade,josie,separateWays,carnival,toomuchtimeonmyhands,blackmagicwoman,longTrainRunning]
ↂapri28ζ2025 = [blueOnBlackInC,ladyMarmlade,discoInferno,changeTheWorld,separateWays,jacky,heavychevy,goldOnTheCeiling,iWillSurvive]
ↂmay2PinesShow = [longTrainRunning,rollWithTheChanges,blueOnBlackInC,evilWays,carnival,bakerStreet,discoInferno,callMeBlondie,doitagain,logicalSong,wonderfulTonight,heavychevy,blackmagicwoman,
                  Twentyfiveor6tofour,rhiannon,jacky,ladyMarmlade,naturalWoman,meandbobbymcgee,youresovain,theLetter,iWillSurvive,breakDown,stopDragginMyHeartAround,reelingInTheYears
                  ,separateWays,loveSneakin,toomuchtimeonmyhands,changeTheWorld,aintItFun,manIFeelLikeAWoman,thrillIsGone,goldOnTheCeiling]
ↂcopper_creek_may_12_2025 = [blueOnBlackInC,carnival,bakerStreet,callMeBlondie,evilWays,youresovain,breakDown]
ↂcopper_creek_may_26_2025_cancelled = [whatYouNeed,imAlright,longTrainRunning, peg,stopDragginMyHeartAround,aintItFun]
ↂcopper_creek_june_2_2025 = [whatYouNeed,imAlright,longTrainRunning,discoInferno,stopDragginMyHeartAround,toomuchtimeonmyhands]
ↂcopper_creek_june_11_2025_moes_bbq = [longTrainRunning, rollWithTheChanges,doitagain,goldOnTheCeiling,jacky,discoInferno,stopDragginMyHeartAround, iWillSurvive,meandbobbymcgee,iFeelTheEarthMove,reelingInTheYears,heavychevy,toomuchtimeonmyhands,blackmagicwoman]
ↂcopper_creek_july_21_2025 = [imAlright,peg,thrillIsGone,whatYouNeed,pickUpThePieces]
ↂcopper_creek_july_23_2025 = [reelingInTheYears,whatYouNeed,pickUpThePieces,callMeBlondie,discoInferno,carnival,logicalSong,imAlright]
ↂcopper_creek_july_28_2025 = [pickUpThePieces,whatYouNeed,imAlright,iFeelTheEarthMove,peg,thrillIsGone,callMe,tequila]
ↂaug1PinesShow = [longTrainRunning, rollWithTheChanges,naturalWoman, carnival, bakerStreet, discoInferno, jacky, whatYouNeed, wonderfulTonight, evilWays, heavychevy, Twentyfiveor6tofour,rhiannon,logicalSong,callMeBlondie,meandbobbymcgee,imAlright,peg,theLetter,iWillSurvive,breakDown,stopDragginMyHeartAround,reelingInTheYears,pickUpThePieces,blueOnBlackInC,loveSneakin,toomuchtimeonmyhands,separateWays,changeTheWorld, goldOnTheCeiling,iFeelTheEarthMove,thrillIsGone, blackmagicwoman]
ↂsep12PinesShow = [tequila,carnival,whatYouNeed,wonderfulTonight,bakerStreet,doitagain,jacky,evilWays,rollWithTheChanges,discoInferno,heavychevy,longTrainRunning,Twentyfiveor6tofour,callMe,thrillIsGone,imAlright,meandbobbymcgee,peg,breakDown,rhiannon,iWillSurvive,toomuchtimeonmyhands, separateWays, pickUpThePieces,theLetter,logicalSong,blueOnBlackInC,changeTheWorld,loveSneakin,reelingInTheYears,stopDragginMyHeartAround,iFeelTheEarthMove,goldOnTheCeiling,blackmagicwoman]
ↂcopper_creek_oct_20_2025 = [smoothfeatrobthomas,loveshack,rockyMountainWay,heartOfRockAndRoll,onTheDarkSide,whatILikeAboutYou,flyAway,shadedJade]
ↂcopper_creek_oct_27_2025 = [loveshack,rockyMountainWay,heartOfRockAndRoll,onTheDarkSide,whatILikeAboutYou,whatIDo,shadedJade,tequila, pickUpThePieces]
ↂcopper_creek_nov_3_2025 = [shadedJade, whatIDo,pickUpThePieces,whatYouNeed,iFeelTheEarthMove,discoInferno,goldOnTheCeiling,smoothfeatrobthomas]
ↂcopper_creek_nov_10_2025 = [whatYouNeed, toomuchtimeonmyhands,shadedJade,whatIDo,bakerStreet,imAlright,heartOfRockAndRoll,loveshack]

#November 25, 2025 Rehearsal - Focus on endings and arrangement details
sweetHomeAlabama = Song('Sweet Home Alabama','Lynyrd Skynyrd','01 - Sweet Home Alabama.mp3')
ↂcopper_creek_nov_25_2025 = [thrillIsGone,shadedJade,iWillSurvive,bakerStreet,longTrainRunning,rhiannon,heartOfRockAndRoll,rollWithTheChanges]

#December 2, 2025 Rehearsal - Focus on timing/transitions and audience favorites
ↂcopper_creek_dec_2_2025 = [whatIDo,callMeBlondie,onTheDarkSide,whatILikeAboutYou,sweetHomeAlabama,toomuchtimeonmyhands,whatYouNeed,loveshack]

#December 8, 2025 Rehearsal
iCantGoForThat = Song('I Can\'t Go For That','Hall & Oates','03 - I Can\'t Go for That (No Can Do).mp3')
ↂcopper_creek_dec_8_2025 = [iCantGoForThat,toomuchtimeonmyhands,carnival,jacky,loveSneakin,reelingInTheYears]

#December 15, 2025 Rehearsal - Light groove/feel-good rehearsal (no sax)
ↂcopper_creek_dec_15_2025 = [whatIDo,shadedJade,whatYouNeed,imAlright,goldOnTheCeiling,discoInferno]

#December 29, 2025 Rehearsal - Full band with horns (sax + trombone)
# Band Members:
#   Jim Mann - Keys
#   Kevin Redmond - Guitar 1
#   Tyler Drake - Guitar 2 / Trombone
#   Cameron - Lead Vox
#   Gene Ng - Bass
#   Wade Bolling - Drums
#   Drew Kasch - Sax
#   All members except Wade are backing vox
ↂcopper_creek_dec_29_2025 = [rockyMountainWay,pickUpThePieces,bakerStreet,tequila,smoothfeatrobthomas,heartOfRockAndRoll]

#January 5, 2026 Rehearsal - Catching up on missed sax songs from Dec 29
# Sax and lead vox were out sick last week - focusing on missed songs plus Peg and Hall & Oates
ↂcopper_creek_jan_5_2026 = [pickUpThePieces,bakerStreet,tequila,peg,iCantGoForThat,discoInferno]

#January 12, 2026 Rehearsal - Full house, carryover songs from Jan 5
ↂcopper_creek_jan_12_2026 = [bakerStreet,Twentyfiveor6tofour,goldOnTheCeiling,shadedJade,whatIDo,smoothfeatrobthomas]

#New Songs
smoothOperator = Song('Smooth Operator','Sade','01 - Smooth Operator.mp3')
boots = Song('These Boots Are Made for Walkin\'','Nancy Sinatra','05 - These Boots Are Made for Walkin\'.mp3')

#January 26, 2026 Rehearsal
ↂcopper_creek_jan_26_2026 = [logicalSong,smoothOperator,callMeBlondie,iCantGoForThat,heartOfRockAndRoll,imAlright,loveshack]

#February 2, 2026 Rehearsal
ↂcopper_creek_feb_2_2026 = [whatYouNeed,onTheDarkSide,whatILikeAboutYou,josie,logicalSong,smoothOperator,imAlright]

# Generate a unique identifier for the set of songs
beautifulCurrent = tag_only(ↂcopper_creek_feb_2_2026)
#groovyCurrent = tag_and_shuffle(flashJam_Feb19)

# Export the combined audio with date in the filename
output_filename = f"combined_performance_prep_{beautifulCurrent[0]}.mp3"
output_path = os.path.join(output_directory, output_filename)

play = False
save = True
prep_music_performance(beautifulCurrent[1],save,play)




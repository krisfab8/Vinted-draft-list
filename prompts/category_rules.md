# Category Mapping Rules
# Format: Item type -> Vinted category path
# All paths verified against vinted_categories.json scraped 2026-03-14

# Men's
Blazer               -> Men > Suits > Blazers
Suit jacket          -> Men > Suits > Blazers
Sports jacket        -> Men > Suits > Blazers
Overcoat             -> Men > Coats > Overcoat
Wax jacket           -> Men > Coats > Overcoat
Wool coat            -> Men > Coats > Overcoat
Trench coat          -> Men > Coats > Trench
Parka                -> Men > Coats > Parka
Peacoat              -> Men > Coats > Peacoat
Raincoat             -> Men > Coats > Raincoat
Duffle coat          -> Men > Coats > Duffle
Chore jacket         -> Men > Jackets > Field
Denim jacket         -> Men > Jackets > Denim
Overshirt            -> Men > Jackets > Field
Bomber jacket        -> Men > Jackets > Bomber
Fleece jacket        -> Men > Jackets > Fleece
Harrington jacket    -> Men > Jackets > Harrington
Puffer jacket        -> Men > Jackets > Puffer
Quilted jacket       -> Men > Jackets > Quilted
Gilet                -> Men > Gilets
Lambswool jumper     -> Men > Knitwear
Merino jumper        -> Men > Knitwear
Crewneck sweatshirt  -> Men > Sweatshirts & Hoodies
Hoodie               -> Men > Sweatshirts & Hoodies
Flannel shirt        -> Men > Shirts > Checked
Oxford shirt         -> Men > Shirts > Plain
Polo shirt           -> Men > Polo Shirts
T-shirt              -> Men > T-shirts
Graphic t-shirt      -> Men > T-shirts > Graphic
Band t-shirt         -> Men > T-shirts > Graphic
Printed t-shirt      -> Men > T-shirts > Graphic
Trainers             -> Men > Shoes > Trainers
Sneakers             -> Men > Shoes > Trainers
Running shoes        -> Men > Shoes > Trainers
Canvas shoes         -> Men > Shoes > Trainers
Plimsolls            -> Men > Shoes > Trainers
Walking boots        -> Men > Shoes > Boots > Desert
Chelsea boots        -> Men > Shoes > Boots > Chelsea
Desert boots         -> Men > Shoes > Boots > Desert
Wellington boots     -> Men > Shoes > Boots > Wellington
Ankle boots          -> Men > Shoes > Boots > Chelsea
Work boots           -> Men > Shoes > Boots > Other
Hiking boots         -> Men > Shoes > Boots > Other
Brogue shoes         -> Men > Shoes > Formal
Oxford shoes         -> Men > Shoes > Formal
Derby shoes          -> Men > Shoes > Formal
Loafers              -> Men > Shoes > Loafers
Sandals              -> Men > Shoes > Sandals
Slippers             -> Men > Shoes > Home Shoes
Mules                -> Men > Shoes > Sandals
Corduroy trousers    -> Men > Trousers
Chino trousers       -> Men > Trousers > Chinos
Slim fit jeans       -> Men > Jeans > Slim
Skinny jeans         -> Men > Jeans > Skinny
Straight fit jeans   -> Men > Jeans > Straight
Ripped jeans         -> Men > Jeans > Ripped
Jeans                -> Men > Jeans
Track pants          -> Men > Trousers > Joggers
Joggers              -> Men > Trousers > Joggers
Sweatpants           -> Men > Trousers > Joggers

# Women's
Blazer               -> Women > Suits > Blazers
Suit jacket          -> Women > Suits > Blazers
Overcoat             -> Women > Coats > Overcoat
Wax jacket           -> Women > Coats > Overcoat
Wool coat            -> Women > Coats > Overcoat
Trench coat          -> Women > Coats > Trench
Parka                -> Women > Coats > Parka
Raincoat             -> Women > Coats > Raincoat
Denim jacket         -> Women > Jackets > Denim
Overshirt            -> Women > Jackets > Field
Puffer jacket        -> Women > Jackets > Puffer
Gilet                -> Women > Gilets
Lambswool jumper     -> Women > Knitwear
Merino jumper        -> Women > Knitwear
Crewneck sweatshirt  -> Women > Sweatshirts & Hoodies
Hoodie               -> Women > Sweatshirts & Hoodies
Shirt / blouse       -> Women > Blouses & Shirts
T-shirt              -> Women > Tops > T-shirt
Midi dress           -> Women > Dresses > Midi
Maxi dress           -> Women > Dresses > Maxi
Mini dress           -> Women > Dresses > Mini
Trainers             -> Women > Shoes > Trainers
Sneakers             -> Women > Shoes > Trainers
Running shoes        -> Women > Shoes > Trainers
Canvas shoes         -> Women > Shoes > Trainers
Plimsolls            -> Women > Shoes > Trainers
Ankle boots          -> Women > Shoes > Boots > Ankle
Chelsea boots        -> Women > Shoes > Boots > Ankle
Knee boots           -> Women > Shoes > Boots > Knee
Wellington boots     -> Women > Shoes > Boots > Wellington
Court shoes          -> Women > Shoes > Court Shoes
High heels           -> Women > Shoes > Heels
Stilettos            -> Women > Shoes > Heels
Wedge heels          -> Women > Shoes > Wedges
Ballet flats         -> Women > Shoes > Flats
Mules                -> Women > Shoes > Mules
Loafers              -> Women > Shoes > Loafers
Sandals              -> Women > Shoes > Sandals
Flip flops           -> Women > Shoes > Flip Flops
Slippers             -> Women > Shoes > Home Shoes
Espadrilles          -> Women > Shoes > Sandals
Corduroy trousers    -> Women > Trousers & Leggings
Straight jeans       -> Women > Jeans > Straight
Skinny jeans         -> Women > Jeans > Skinny
Slim fit jeans       -> Women > Jeans > Slim
Boyfriend jeans      -> Women > Jeans > Boyfriend
Cropped jeans        -> Women > Jeans > Cropped
Flared jeans         -> Women > Jeans > Flared
High waisted jeans   -> Women > Jeans > High waisted
Ripped jeans         -> Women > Jeans > Ripped
Jeans                -> Women > Jeans
Track pants          -> Women > Trousers > Joggers
Joggers              -> Women > Trousers > Joggers
Sweatpants           -> Women > Trousers > Joggers
Leggings             -> Women > Trousers > Leggings
Mini skirt           -> Women > Skirts > Mini
Midi skirt           -> Women > Skirts > Midi
Maxi skirt           -> Women > Skirts > Maxi
Skirt                -> Women > Skirts

# Notes
# - Shoes fallback: if subtype unclear, use Men > Shoes or Women > Shoes (no sub-category).
# - Trainers covers: sneakers, running shoes, canvas shoes, plimsolls.
# - When in doubt, prefer the more specific sub-category.
# - Men's jeans: only Slim fit, Skinny, Straight fit, Ripped exist on Vinted UK.
# - Women's jeans: no "Slim fit" — use Straight jeans as fallback.
# - Coats are 5 levels deep: Men/Women > Clothing > Outerwear > Coats > [type]
# - Hoodies/sweatshirts go under Jumpers & sweaters, NOT Tops & t-shirts.
# - If item type is ambiguous, flag for manual review.

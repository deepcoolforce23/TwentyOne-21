import asyncio
import websockets
import json
import secrets
from datetime import datetime
import sys
import random

# ============ GAME SETUP ============

def create_deck():
    """Create a deck with 11 cards (values 1-11)"""
    deck = [str(i) for i in range(1, 12)]  # Cards 1-11
    random.shuffle(deck)
    return deck

def create_trump_deck():
    """Create trump cards"""
    trump_cards = [
        'Perfect Draw', 'Perfect Draw',
        'Switcharoo', 'Switcharoo',
        'Refresh', 'Refresh',
        'Betrayal', 'Betrayal',
        '17', '17',
        '24', '24',
        '27', '27',
        'Destroy', 'Destroy'
    ]
    random.shuffle(trump_cards)
    return trump_cards

def calc_hand_value(hand):
    """Calculate total value of cards in hand"""
    total = 0
    for card in hand:
        if card.startswith('Perfect'):
            # Perfect cards are worth their limit value
            try:
                value = int(card.split('/')[0].split()[-1])
                total += value
            except:
                total += 0
        else:
            # Parse cards (now just numbers 1-11)
            try:
                total += int(card)
            except:
                total += 0
    return total

def evaluate_exchange(host_hand, player_hand, limit):
    """
    Evaluate hands and determine winner
    Returns: ('host' or 'player'), host_value, player_value
    """
    host_value = calc_hand_value(host_hand)
    player_value = calc_hand_value(player_hand)
    
    # Both under limit: closer to limit wins
    if host_value <= limit and player_value <= limit:
        if abs(host_value - limit) < abs(player_value - limit):
            return 'host', host_value, player_value
        elif abs(player_value - limit) < abs(host_value - limit):
            return 'player', host_value, player_value
        else:
            return 'tie', host_value, player_value
    
    # One exactly at limit: wins automatically
    if host_value == limit:
        return 'host', host_value, player_value
    if player_value == limit:
        return 'player', host_value, player_value
    
    # Both over limit: lower value wins
    if host_value > limit and player_value > limit:
        if host_value < player_value:
            return 'host', host_value, player_value
        elif player_value < host_value:
            return 'player', host_value, player_value
        else:
            return 'tie', host_value, player_value
    
    # One over limit, one under: under wins
    if host_value <= limit:
        return 'host', host_value, player_value
    else:
        return 'player', host_value, player_value

async def handle_trump_effect(game, player_role, trump_card, host_ws, player_ws):
    """
    Apply the effect of a trump card
    Returns a list of messages to send to players
    """
    messages = []
    opponent_role = 'player' if player_role == 'host' else 'host'
    opponent_hand = game['player_hand'] if player_role == 'host' else game['host_hand']
    player_hand = game['host_hand'] if player_role == 'host' else game['player_hand']
    
    if trump_card == 'Perfect Draw':
        # Find the best card from deck that gets hand closest to limit without busting
        current_value = calc_hand_value(player_hand)
        limit = game['limit']
        
        # Get only numeric cards from deck (ignore special cards)
        numeric_cards = []
        for card in game['deck']:
            try:
                numeric_cards.append((card, int(card)))
            except:
                pass  # Skip non-numeric cards
        
        if not numeric_cards:
            messages.append(('player', {
                'type': 'trump_effect',
                'effect': 'Perfect Draw',
                'message': '[TRUMP] Perfect Draw! No numeric cards in deck!',
                'your_hand': player_hand
            }))
        else:
            best_card = None
            best_distance = float('inf')
            
            # Check all numeric cards in deck to find the best one
            for card_str, card_value in numeric_cards:
                new_value = current_value + card_value
                
                if new_value <= limit:
                    # Card keeps us under limit - this is ideal
                    distance = limit - new_value
                    if distance < best_distance:
                        best_distance = distance
                        best_card = (card_str, card_value)
                elif new_value > limit:
                    # Card would bust us - find least bad option
                    distance = new_value - limit
                    if distance < best_distance:
                        best_distance = distance
                        best_card = (card_str, card_value)
            
            if best_card is not None:
                # Remove the selected card from deck and add to hand
                game['deck'].remove(best_card[0])
                player_hand.append(best_card[0])
                messages.append(('player', {
                    'type': 'trump_effect',
                    'effect': 'Perfect Draw',
                    'message': f'[TRUMP] Perfect Draw! You got a {best_card[1]} to get closer to {limit}!',
                    'your_hand': player_hand
                }))
            else:
                # Fallback: just draw a random numeric card
                card = numeric_cards[0][0]
                game['deck'].remove(card)
                player_hand.append(card)
                messages.append(('player', {
                    'type': 'trump_effect',
                    'effect': 'Perfect Draw',
                    'message': f'[TRUMP] Perfect Draw! You drew {numeric_cards[0][1]}!',
                    'your_hand': player_hand
                }))
        
        messages.append(('opponent', {
            'type': 'trump_effect',
            'effect': 'Perfect Draw',
            'message': f'[TRUMP] Opponent used Perfect Draw!'
        }))
    
    elif trump_card == 'Switcharoo':
        if player_hand and opponent_hand:
            # Swap a random card from opponent with player's choice
            random_opp_card = random.choice(opponent_hand)
            opponent_hand.remove(random_opp_card)
            messages.append(('player', {
                'type': 'trump_effect',
                'effect': 'Switcharoo',
                'message': f'[TRUMP] Switcharoo! You swapped with opponent\'s random card!',
                'opponent_card': random_opp_card,
                'your_hand': player_hand
            }))
            messages.append(('opponent', {
                'type': 'trump_effect',
                'effect': 'Switcharoo',
                'message': f'[TRUMP] Opponent used Switcharoo! They took one of your cards!'
            }))
    
    elif trump_card == 'Refresh':
        # Return cards to deck and draw 2 new ones
        for card in player_hand:
            game['deck'].append(card)
        player_hand.clear()
        for _ in range(2):
            if game['deck']:
                player_hand.append(game['deck'].pop())
        random.shuffle(game['deck'])
        messages.append(('player', {
            'type': 'trump_effect',
            'effect': 'Refresh',
            'message': '[TRUMP] Refresh! Your hand is replaced with 2 new cards!',
            'your_hand': player_hand
        }))
        messages.append(('opponent', {
            'type': 'trump_effect',
            'effect': 'Refresh',
            'message': '[TRUMP] Opponent used Refresh! Their hand is reset!'
        }))
    
    elif trump_card == 'Betrayal':
        # Force opponent to draw
        if game['deck']:
            card = game['deck'].pop()
            opponent_hand.append(card)
            messages.append(('player', {
                'type': 'trump_effect',
                'effect': 'Betrayal',
                'message': '[TRUMP] Betrayal! You forced your opponent to draw!'
            }))
            messages.append(('opponent', {
                'type': 'trump_effect',
                'effect': 'Betrayal',
                'message': f'[TRUMP] Opponent used Betrayal! You were forced to draw: {card}',
                'your_hand': opponent_hand
            }))
    
    elif trump_card in ['17', '24', '27']:
        # Set new limit
        new_limit = int(trump_card)
        game['limit'] = new_limit
        game['active_effects'].append(trump_card)
        messages.append(('player', {
            'type': 'trump_effect',
            'effect': trump_card,
            'message': f'[TRUMP] Limit changed to {new_limit}!'
        }))
        messages.append(('opponent', {
            'type': 'trump_effect',
            'effect': trump_card,
            'message': f'[TRUMP] Limit changed to {new_limit}!'
        }))
    
    elif trump_card == 'Destroy':
        # Remove all active effects
        game['active_effects'] = []
        game['limit'] = 21  # Reset to default
        messages.append(('player', {
            'type': 'trump_effect',
            'effect': 'Destroy',
            'message': '[TRUMP] Destroy! All effects removed! Limit reset to 21!'
        }))
        messages.append(('opponent', {
            'type': 'trump_effect',
            'effect': 'Destroy',
            'message': '[TRUMP] Destroy! All effects removed! Limit reset to 21!'
        }))
    
    return messages

# ============ BOT PLAYER ============

class BotPlayer:
    """AI bot player for single-player bot mode"""
    
    def __init__(self):
        self.hand = []
        self.trump_hand = []
        self.distance = 7
        self.passed = False
        self.last_opponent_action = None
    
    def decide_action(self, game_state):
        """
        Decide what action to take based on current game state
        Analyzes visible cards and deck composition for smarter decisions
        Returns: 'draw', 'pass', or ('trump', card_name)
        """
        hand_value = calc_hand_value(self.hand)
        limit = game_state['limit']
        opponent_passed = game_state['opponent_passed']
        player_last_action = game_state['player_last_action']
        player_hand = game_state.get('player_hand', [])
        remaining_deck = game_state.get('remaining_deck', [])
        
        # Reaction to player's negative passive effects
        if player_last_action in ['17', '24', '27']:
            # Player used a negative passive effect
            if 'Destroy' in self.trump_hand:
                return ('trump', 'Destroy')
            elif '17' in self.trump_hand or '24' in self.trump_hand or '27' in self.trump_hand:
                # Use our own passive effect to override
                for card in ['17', '24', '27']:
                    if card in self.trump_hand:
                        return ('trump', card)
        
        # Reaction to player's Betrayal
        if player_last_action == 'Betrayal':
            if 'Destroy' in self.trump_hand:
                return ('trump', 'Destroy')
            elif '17' in self.trump_hand or '24' in self.trump_hand or '27' in self.trump_hand:
                for card in ['17', '24', '27']:
                    if card in self.trump_hand:
                        return ('trump', card)
        
        # If opponent just passed, check if we should also pass
        if opponent_passed:
            return 'pass'
        
        # Perfect Draw strategy: use if available
        if 'Perfect Draw' in self.trump_hand:
            return ('trump', 'Perfect Draw')
        
        # If hand value < 10, draw more cards (safe zone)
        if hand_value < 10:
            return 'draw'
        
        # If hand is over limit, pass or use Refresh
        if hand_value > limit:
            if 'Refresh' in self.trump_hand:
                return ('trump', 'Refresh')
            else:
                return 'pass'
        
        # Analyze deck composition to make smarter decisions
        if remaining_deck:
            # Count what cards are in the deck
            deck_composition = {}
            for card in remaining_deck:
                try:
                    card_val = int(card)
                    deck_composition[card_val] = deck_composition.get(card_val, 0) + 1
                except:
                    pass
            
            # Count visible cards (player's hand and our hand)
            visible_cards = player_hand + self.hand
            used_composition = {}
            for card in visible_cards:
                try:
                    card_val = int(card)
                    used_composition[card_val] = used_composition.get(card_val, 0) + 1
                except:
                    pass
            
            # Calculate how many safe cards are left in deck
            safe_threshold = limit - hand_value
            safe_cards_in_deck = 0
            total_cards_in_deck = len(remaining_deck)
            
            for card_val in range(1, 12):
                # Check if drawing this card keeps us under limit
                if hand_value + card_val <= limit:
                    safe_cards_in_deck += deck_composition.get(card_val, 0)
            
            # If we have good odds of drawing a safe card, draw
            if total_cards_in_deck > 0:
                safe_probability = safe_cards_in_deck / total_cards_in_deck
                
                # Draw if probability is good and we're not too close to limit
                if hand_value < limit - 2:
                    if safe_probability > 0.4:  # 40% chance of safe card
                        return 'draw'
                elif hand_value < limit:  # Between limit-2 and limit
                    if safe_probability > 0.6:  # Need 60%+ chance when closer to limit
                        return 'draw'
        
        # If hand value <= passive effect cards, use them strategically
        for card in ['17', '24', '27']:
            if card in self.trump_hand and hand_value <= int(card):
                # Use passive cards when close to limit to secure a win
                if hand_value >= limit - 3:
                    return ('trump', card)
        
        # If very close to limit, prefer to pass
        if hand_value >= limit - 1:
            if 'Refresh' in self.trump_hand and hand_value >= limit - 2:
                return ('trump', 'Refresh')
            return 'pass'
        
        # Default: draw if reasonable hand value
        if hand_value < limit - 1:
            return 'draw'
        else:
            return 'pass'

# ============ SERVER ============

games = {}  # {code: {host_ws, player_ws, state, current_turn}}

async def handle_client(websocket, path):
    code = None
    player_role = None
    
    try:
        while True:
            message = json.loads(await websocket.recv())
            
            # Host creates a new game
            if message['action'] == 'host':
                code = secrets.token_hex(3).upper()  # 6-char code like "A3F2B1"
                games[code] = {
                    'host_ws': websocket,
                    'player_ws': None,
                    'deck': create_deck(),
                    'trump_deck': create_trump_deck(),
                    'host_hand': [],
                    'player_hand': [],
                    'host_trump_hand': [],
                    'player_trump_hand': [],
                    'host_distance': 7,
                    'player_distance': 7,
                    'current_bet': 1,
                    'host_passed': False,
                    'player_passed': False,
                    'in_exchange': True,
                    'exchange_count': 0,
                    'current_turn': 'host',
                    'limit': 21,
                    'active_effects': [],
                    'moves': []
                }
                player_role = 'host'
                await websocket.send(json.dumps({
                    'type': 'code_generated',
                    'code': code,
                    'message': f'Game code: {code}. Waiting for opponent...'
                }))
            
            # Player joins existing game
            elif message['action'] == 'join':
                join_code = message['code'].upper()
                if join_code not in games:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Game code not found!'
                    }))
                elif games[join_code]['player_ws'] is not None:
                    await websocket.send(json.dumps({
                        'type': 'error',
                        'message': 'Game already has 2 players!'
                    }))
                else:
                    code = join_code
                    games[code]['player_ws'] = websocket
                    player_role = 'player'
                    
                    # Deal initial cards and trump cards
                    game = games[code]
                    if game['deck']:
                        game['host_hand'].append(game['deck'].pop())
                        game['player_hand'].append(game['deck'].pop())
                    
                    # Deal 2 trump cards per round
                    for _ in range(2):
                        if game['trump_deck']:
                            game['host_trump_hand'].append(game['trump_deck'].pop())
                        if game['trump_deck']:
                            game['player_trump_hand'].append(game['trump_deck'].pop())
                    
                    # Format opponent hand with first card hidden as '?'
                    opponent_hand_host = ['?'] + game['player_hand'][1:] if len(game['player_hand']) > 1 else ['?']
                    opponent_hand_player = ['?'] + game['host_hand'][1:] if len(game['host_hand']) > 1 else ['?']
                    
                    # Notify both players game is starting
                    await games[code]['host_ws'].send(json.dumps({
                        'type': 'game_start',
                        'message': 'Opponent joined! You are HOST (go first)',
                        'role': 'host',
                        'your_hand': game['host_hand'],
                        'your_trump_hand': game['host_trump_hand'],
                        'opponent_hand': opponent_hand_host,
                        'limit': game['limit'],
                        'host_distance': game['host_distance'],
                        'player_distance': game['player_distance'],
                        'current_bet': game['current_bet']
                    }))
                    await websocket.send(json.dumps({
                        'type': 'game_start',
                        'message': 'Connected! You are PLAYER (waiting for host)',
                        'role': 'player',
                        'your_hand': game['player_hand'],
                        'your_trump_hand': game['player_trump_hand'],
                        'opponent_hand': opponent_hand_player,
                        'limit': game['limit'],
                        'host_distance': game['host_distance'],
                        'player_distance': game['player_distance'],
                        'current_bet': game['current_bet']
                    }))
            
            # Player makes a move (draw, pass, or play_trump)
            elif message['action'] in ['draw_card', 'pass', 'play_trump']:
                if code and code in games:
                    game = games[code]
                    player_hand = game['host_hand'] if player_role == 'host' else game['player_hand']
                    player_trump_hand = game['host_trump_hand'] if player_role == 'host' else game['player_trump_hand']
                    opponent_ws = game['player_ws'] if player_role == 'host' else game['host_ws']
                    
                    # Handle draw_card action
                    if message['action'] == 'draw_card':
                        if game['deck']:
                            # Slim chance of getting a trump card (15% chance)
                            if random.random() < 0.15 and game['trump_deck']:
                                trump_card = game['trump_deck'].pop()
                                player_trump_hand.append(trump_card)
                                await websocket.send(json.dumps({
                                    'type': 'trump_card_drawn',
                                    'card': trump_card,
                                    'your_hand': player_hand,
                                    'your_trump_hand': player_trump_hand
                                }))
                                if opponent_ws:
                                    await opponent_ws.send(json.dumps({
                                        'type': 'opponent_action',
                                        'action': 'draw_card',
                                        'from': player_role,
                                        'got_trump': True,
                                        'opponent_hand': ['?'] + player_hand[1:] if len(player_hand) > 1 else ['?']
                                    }))
                            else:
                                card = game['deck'].pop()
                                player_hand.append(card)
                                await websocket.send(json.dumps({
                                    'type': 'card_drawn',
                                    'card': card,
                                    'your_hand': player_hand,
                                    'limit': game['limit']
                                }))
                                if opponent_ws:
                                    await opponent_ws.send(json.dumps({
                                        'type': 'opponent_action',
                                        'action': 'draw_card',
                                        'from': player_role,
                                        'opponent_hand': ['?'] + player_hand[1:] if len(player_hand) > 1 else ['?']
                                    }))
                        else:
                            await websocket.send(json.dumps({
                                'type': 'error',
                                'message': 'No cards left in deck!'
                            }))
                    
                    # Handle pass action
                    elif message['action'] == 'pass':
                        if player_role == 'host':
                            game['host_passed'] = True
                        else:
                            game['player_passed'] = True
                        
                        await websocket.send(json.dumps({
                            'type': 'action_confirmed',
                            'action': 'pass',
                            'message': 'You passed!'
                        }))
                        if opponent_ws:
                            await opponent_ws.send(json.dumps({
                                'type': 'opponent_action',
                                'action': 'pass',
                                'from': player_role,
                                'opponent_hand': ['?'] + player_hand[1:] if len(player_hand) > 1 else ['?']
                            }))
                        
                        # Check if both players have passed
                        if game['host_passed'] and game['player_passed']:
                            # Evaluate hands
                            winner, host_val, player_val = evaluate_exchange(
                                game['host_hand'], game['player_hand'], game['limit']
                            )
                            
                            result_msg = f"Exchange Results:\nHost: {host_val} | Player: {player_val}\n"
                            
                            if winner == 'host':
                                game['host_distance'] += game['current_bet']
                                game['player_distance'] -= game['current_bet']
                                result_msg += f"HOST WINS! +{game['current_bet']} distance"
                            elif winner == 'player':
                                game['player_distance'] += game['current_bet']
                                game['host_distance'] -= game['current_bet']
                                result_msg += f"PLAYER WINS! +{game['current_bet']} distance"
                            else:
                                result_msg += "TIE! No distance change"
                            
                            # Check for game end
                            if game['host_distance'] <= 0:
                                await game['host_ws'].send(json.dumps({
                                    'type': 'game_end',
                                    'message': f'[GAME OVER] PLAYER WINS! You lost all your distance!'
                                }))
                                await opponent_ws.send(json.dumps({
                                    'type': 'game_end',
                                    'message': f'[GAME OVER] YOU WIN! Opponent lost all their distance!'
                                }))
                                del games[code]
                            elif game['player_distance'] <= 0:
                                await game['host_ws'].send(json.dumps({
                                    'type': 'game_end',
                                    'message': f'[GAME OVER] HOST WINS! Opponent lost all their distance!'
                                }))
                                await opponent_ws.send(json.dumps({
                                    'type': 'game_end',
                                    'message': f'[GAME OVER] YOU LOST! You lost all your distance!'
                                }))
                                del games[code]
                            else:
                                # Start new exchange
                                game['host_hand'].clear()
                                game['player_hand'].clear()
                                game['host_passed'] = False
                                game['player_passed'] = False
                                game['exchange_count'] += 1
                                
                                # Deal new cards
                                if game['deck']:
                                    game['host_hand'].append(game['deck'].pop())
                                    game['player_hand'].append(game['deck'].pop())
                                
                                # Notify both players of exchange result and new exchange start
                                opponent_hand_for_host = ['?'] + game['player_hand'][1:] if len(game['player_hand']) > 1 else ['?']
                                opponent_hand_for_player = ['?'] + game['host_hand'][1:] if len(game['host_hand']) > 1 else ['?']
                                await game['host_ws'].send(json.dumps({
                                    'type': 'exchange_result',
                                    'result': result_msg,
                                    'new_exchange': True,
                                    'host_distance': game['host_distance'],
                                    'player_distance': game['player_distance'],
                                    'your_hand': game['host_hand'],
                                    'opponent_hand': opponent_hand_for_host,
                                    'current_bet': game['current_bet']
                                }))
                                await opponent_ws.send(json.dumps({
                                    'type': 'exchange_result',
                                    'result': result_msg,
                                    'new_exchange': True,
                                    'host_distance': game['host_distance'],
                                    'player_distance': game['player_distance'],
                                    'your_hand': game['player_hand'],
                                    'opponent_hand': opponent_hand_for_player,
                                    'current_bet': game['current_bet']
                                }))
                    
                    # Handle play_trump action
                    elif message['action'] == 'play_trump':
                        trump_card_name = message.get('trump_card')
                        if trump_card_name and trump_card_name in player_trump_hand:
                            player_trump_hand.remove(trump_card_name)
                            
                            # Apply trump card effect
                            effects = await handle_trump_effect(game, player_role, trump_card_name, game['host_ws'], game['player_ws'])
                            
                            for target, msg in effects:
                                if target == 'player':
                                    await websocket.send(json.dumps(msg))
                                elif target == 'opponent' and opponent_ws:
                                    await opponent_ws.send(json.dumps(msg))
                            
                            # Deal 2 trump cards at end of round
                            for _ in range(2):
                                if game['trump_deck']:
                                    new_trump = game['trump_deck'].pop()
                                    player_trump_hand.append(new_trump)
                            
                            await websocket.send(json.dumps({
                                'type': 'trump_hand_update',
                                'your_trump_hand': player_trump_hand
                            }))
                        else:
                            await websocket.send(json.dumps({
                                'type': 'error',
                                'message': 'Invalid or missing trump card!'
                            }))
            
            # Keep-alive ping
            elif message['action'] == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))
    
    except websockets.exceptions.ConnectionClosed:
        # Clean up when player disconnects
        if code and code in games:
            game = games[code]
            if game['host_ws'] == websocket:
                if game['player_ws']:
                    await game['player_ws'].send(json.dumps({
                        'type': 'opponent_disconnect',
                        'message': 'Host disconnected!'
                    }))
                del games[code]
            elif game['player_ws'] == websocket:
                if game['host_ws']:
                    await game['host_ws'].send(json.dumps({
                        'type': 'opponent_disconnect',
                        'message': 'Opponent disconnected!'
                    }))
                del games[code]

async def share_game_state(code, state_data):
    """
    EXAMPLE: Function to share game information between players
    
    This demonstrates how to send shared information like:
    - Cards in a player's hand
    - Game effects or status updates
    - Score/health values
    - Board state or game objects
    
    Usage:
        state_data = {
            'host_hand': ['card1', 'card2', 'card3'],
            'player_hand': ['cardA', 'cardB'],
            'board': {'position': 'value'},
            'effects': ['burn', 'freeze']
        }
        await share_game_state(code, state_data)
    """
    pass
    # TODO: Implement to send state_data to both players
    # if code in games:
    #     game = games[code]
    #     await game['host_ws'].send(json.dumps({'type': 'state_update', 'data': state_data}))
    #     await game['player_ws'].send(json.dumps({'type': 'state_update', 'data': state_data}))

async def run_server():
    async with websockets.serve(handle_client, "localhost", 8765):
        print("[SERVER] Game Server running on ws://localhost:8765")
        print("Press Ctrl+C to stop")
        await asyncio.Future()  # run forever

# ============ CLIENT ============

class GameClient:
    def __init__(self):
        self.websocket = None
        self.role = None
        self.code = None
        self.hand = []
        self.trump_hand = []
        self.opponent_hand = []
        self.limit = 21
        self.host_distance = 7
        self.player_distance = 7
        self.current_bet = 1
    
    async def connect(self):
        try:
            self.websocket = await websockets.connect("ws://localhost:8765")
            print("[OK] Connected to server!")
        except:
            print("[ERROR] Could not connect to server. Make sure it's running!")
            return False
        return True
    
    async def send_message(self, message):
        await self.websocket.send(json.dumps(message))
    
    async def receive_messages(self):
        """Listen for incoming messages from server"""
        try:
            while True:
                response = json.loads(await self.websocket.recv())
                
                if response['type'] == 'code_generated':
                    self.code = response['code']
                    self.role = 'host'
                    print(f"\n[CODE] Your game code: {response['code']}")
                    print("Waiting for opponent to join...")
                
                elif response['type'] == 'game_start':
                    self.role = response['role']
                    self.hand = response.get('your_hand', [])
                    self.trump_hand = response.get('your_trump_hand', [])
                    self.opponent_hand = response.get('opponent_hand', [])
                    self.limit = response.get('limit', 21)
                    self.host_distance = response.get('host_distance', 7)
                    self.player_distance = response.get('player_distance', 7)
                    self.current_bet = response.get('current_bet', 1)
                    print(f"\n[GAME] Game started! {response['message']}")
                    print(f"Your hand: {self.hand}")
                    print(f"Opponent's cards: {' + '.join(self.opponent_hand)}" if self.opponent_hand else "Opponent's cards: ?")
                    print(f"Your trump hand: {self.trump_hand}")
                    print(f"Host Distance: {self.host_distance} | Player Distance: {self.player_distance}")
                    print(f"Current Bet: {self.current_bet} | Limit: {self.limit}")
                
                elif response['type'] == 'card_drawn':
                    self.hand = response.get('your_hand', [])
                    self.limit = response.get('limit', self.limit)
                    print(f"\n[CARD] You drew: {response['card']}")
                    print(f"Your hand: {self.hand} (Limit: {self.limit})")
                
                elif response['type'] == 'trump_card_drawn':
                    self.hand = response.get('your_hand', [])
                    self.trump_hand = response.get('your_trump_hand', [])
                    print(f"\n[TRUMP] You drew a trump card: {response['card']}!!!")
                    print(f"Your hand: {self.hand}")
                    print(f"Your trump hand: {self.trump_hand}")
                
                elif response['type'] == 'trump_hand_update':
                    self.trump_hand = response.get('your_trump_hand', [])
                    print(f"\n[TRUMP] Your trump hand updated: {self.trump_hand}")
                
                elif response['type'] == 'trump_effect':
                    print(f"\n{response['message']}")
                    if 'your_hand' in response:
                        self.hand = response['your_hand']
                    if 'your_trump_hand' in response:
                        self.trump_hand = response['your_trump_hand']
                
                elif response['type'] == 'action_confirmed':
                    print(f"\n[OK] {response['message']}")
                
                elif response['type'] == 'opponent_action':
                    if response.get('got_trump'):
                        print(f"\n[OPPONENT] Opponent drew a trump card!")
                    else:
                        print(f"\n[OPPONENT] Opponent action: {response['action']}")
                    # Show and store opponent's hand with first card as '?'
                    if 'opponent_hand' in response:
                        self.opponent_hand = response['opponent_hand']
                        print(f"[OPPONENT] Opponent's cards: {' + '.join(self.opponent_hand)}")
                
                elif response['type'] == 'exchange_result':
                    print(f"\n{'='*50}")
                    print(response['result'])
                    self.host_distance = response.get('host_distance', self.host_distance)
                    self.player_distance = response.get('player_distance', self.player_distance)
                    self.hand = response.get('your_hand', self.hand)
                    self.opponent_hand = response.get('opponent_hand', self.opponent_hand)
                    self.current_bet = response.get('current_bet', self.current_bet)
                    print(f"Host Distance: {self.host_distance} | Player Distance: {self.player_distance}")
                    if response.get('new_exchange'):
                        print(f"New Exchange started! Your new hand: {self.hand}")
                        if self.opponent_hand:
                            print(f"Opponent's cards: {' + '.join(self.opponent_hand)}")
                    print(f"{'='*50}")
                
                elif response['type'] == 'game_end':
                    print(f"\n{'='*50}")
                    print(response['message'])
                    print(f"{'='*50}")
                    break
                
                elif response['type'] == 'opponent_disconnect':
                    print(f"\n[WARNING] {response['message']}")
                    break
                
                elif response['type'] == 'error':
                    print(f"\n[ERROR] Error: {response['message']}")
        
        except websockets.exceptions.ConnectionClosed:
            print("\n[ERROR] Disconnected from server")
    
    async def host_game(self):
        """Create a new game"""
        await self.send_message({'action': 'host'})
        # Start receiving messages in background
        asyncio.create_task(self.receive_messages())
    
    async def join_game(self, code):
        """Join an existing game with code"""
        await self.send_message({'action': 'join', 'code': code})
        asyncio.create_task(self.receive_messages())
    
    async def play_trump(self, trump_card):
        """Play a trump card"""
        await self.send_message({'action': 'play_trump', 'trump_card': trump_card})
    
    async def make_move(self, action):
        """Send an action to opponent"""
        await self.send_message({'action': action})
    
    async def main_menu(self):
        """Main game menu"""
        print("\n" + "="*40)
        print("      ONLINE 1V1 GAME")
        print("="*40)
        print("1. Host a game (get a code)")
        print("2. Join a game (enter code)")
        print("="*40)
        
        choice = input("Choose (1 or 2): ").strip()
        
        if choice == '1':
            await self.host_game()
        elif choice == '2':
            code = input("Enter game code: ").strip().upper()
            await self.join_game(code)
        else:
            print("Invalid choice!")
            return
        
        # Give time for game to start
        await asyncio.sleep(1)
        
        # Game loop
        while self.websocket and not self.websocket.closed:
            try:
                print("\n" + "="*50)
                print(f"Hand: {self.hand} (Limit: {self.limit})")
                if self.opponent_hand:
                    print(f"Opponent's cards: {' + '.join(self.opponent_hand)}")
                print(f"Trump Cards: {self.trump_hand}")
                print("="*50)
                print("Available actions:")
                print("1. Draw a card")
                print("2. Pass")
                print("3. Play trump card")
                print("4. Quit")
                print("="*50)
                
                choice = input("Choose action (1-4): ").strip()
                
                if choice == '1':
                    await self.make_move('draw_card')
                elif choice == '2':
                    await self.make_move('pass')
                elif choice == '3':
                    if self.trump_hand:
                        print("\nYour trump cards:")
                        for i, card in enumerate(self.trump_hand):
                            print(f"{i+1}. {card}")
                        trump_choice = input("Choose trump card (number): ").strip()
                        try:
                            idx = int(trump_choice) - 1
                            if 0 <= idx < len(self.trump_hand):
                                await self.play_trump(self.trump_hand[idx])
                            else:
                                print("[ERROR] Invalid trump card number!")
                        except ValueError:
                            print("[ERROR] Invalid input!")
                    else:
                        print("[ERROR] You don't have any trump cards!")
                elif choice == '4':
                    break
                else:
                    print("[ERROR] Invalid choice!")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                break

async def play_bot_mode():
    """Run a single-player game against the bot"""
    print("\n" + "="*50)
    print("   STARTING BOT MODE")
    print("="*50)
    
    # Initialize game
    deck = create_deck()
    trump_deck = create_trump_deck()
    player_hand = [deck.pop()]
    bot_hand = [deck.pop()]
    player_trump_hand = []
    bot_trump_hand = []
    
    # Deal trump cards
    for _ in range(2):
        if trump_deck:
            player_trump_hand.append(trump_deck.pop())
        if trump_deck:
            bot_trump_hand.append(trump_deck.pop())
    
    player_distance = 7
    bot_distance = 7
    current_bet = 1
    limit = 21
    active_effects = []
    exchange_count = 0
    
    bot = BotPlayer()
    bot.hand = bot_hand
    bot.trump_hand = bot_trump_hand
    
    print(f"[GAME] Starting game against BOT!")
    print(f"Player Distance: {player_distance} | Bot Distance: {bot_distance}")
    print(f"Limit: {limit} | Current Bet: {current_bet}")
    
    while player_distance > 0 and bot_distance > 0:
        exchange_count += 1
        player_passed = False
        bot_passed = False
        player_last_action = None
        
        print(f"\n" + "="*50)
        print(f"EXCHANGE #{exchange_count}")
        print(f"Your hand: {player_hand} (Value: {calc_hand_value(player_hand)})")
        # Show bot's hand with first card as '?'
        bot_hand_display = ['?'] + bot_hand[1:] if bot_hand else ['?']
        print(f"Bot cards: {' + '.join(bot_hand_display)}")
        print(f"Your trump cards: {player_trump_hand}")
        print(f"Limit: {limit}")
        print("="*50)
        
        # Exchange loop
        while not (player_passed and bot_passed):
            # Player turn
            if not player_passed:
                print(f"\n[YOUR TURN] Hand value: {calc_hand_value(player_hand)}")
                print("1. Draw | 2. Pass | 3. Play Trump")
                player_choice = input("Choice (1-3): ").strip()
                
                if player_choice == '1':
                    if deck:
                        card = deck.pop()
                        player_hand.append(card)
                        print(f"[DRAW] +{card}")
                        player_last_action = 'draw'
                    else:
                        print("[ERROR] Deck empty!")
                elif player_choice == '2':
                    player_passed = True
                    print("[PASS]")
                    player_last_action = 'pass'
                elif player_choice == '3':
                    if player_trump_hand:
                        print("\n[TRUMP CARDS]")
                        for i, card in enumerate(player_trump_hand):
                            print(f"{i+1}. {card}")
                        trump_idx = input("Choose card (number): ").strip()
                        try:
                            idx = int(trump_idx) - 1
                            if 0 <= idx < len(player_trump_hand):
                                trump_card = player_trump_hand.pop(idx)
                                print(f"\n[TRUMP PLAYED] {trump_card}")
                                
                                # Apply trump effects
                                if trump_card == 'Perfect Draw':
                                    perfect_card = f'Perfect {limit}/Perfect {limit}'
                                    player_hand.append(perfect_card)
                                    print(f"[EFFECT] Got a {limit}/Perfect card!")
                                
                                elif trump_card == 'Refresh':
                                    player_hand.clear()
                                    for _ in range(2):
                                        if deck:
                                            player_hand.append(deck.pop())
                                    print(f"[EFFECT] Your hand refreshed! New hand: {player_hand}")
                                
                                elif trump_card == 'Betrayal':
                                    if deck:
                                        card = deck.pop()
                                        bot_hand.append(card)
                                        print(f"[EFFECT] Bot forced to draw!")
                                
                                elif trump_card == 'Switcharoo':
                                    if bot_hand:
                                        bot_card = random.choice(bot_hand)
                                        bot_hand.remove(bot_card)
                                        print(f"[EFFECT] You swapped with bot's random card!")
                                
                                elif trump_card in ['17', '24', '27']:
                                    limit = int(trump_card)
                                    print(f"[EFFECT] Limit changed to {limit}!")
                                
                                elif trump_card == 'Destroy':
                                    limit = 21
                                    print(f"[EFFECT] All effects cleared! Limit reset to 21!")
                                
                                # Deal 2 new trump cards to player
                                for _ in range(2):
                                    if trump_deck:
                                        player_trump_hand.append(trump_deck.pop())
                                
                                player_last_action = trump_card
                            else:
                                print("[ERROR] Invalid card number!")
                        except ValueError:
                            print("[ERROR] Invalid input!")
                    else:
                        print("[ERROR] You don't have any trump cards!")
                else:
                    print("[ERROR] Invalid!")
                    continue
            
            # Bot turn
            if not bot_passed:
                await asyncio.sleep(0.5)
                game_state = {
                    'limit': limit,
                    'opponent_passed': player_passed,
                    'player_last_action': player_last_action,
                    'player_hand': player_hand,
                    'remaining_deck': deck
                }
                action = bot.decide_action(game_state)
                
                if action == 'draw':
                    if deck:
                        card = deck.pop()
                        bot_hand.append(card)
                        # Show bot's hand with first card hidden as '?' and rest visible
                        bot_hand_display = ['?'] + bot_hand[1:]
                        print(f"[BOT] Drew a {card}!")
                        print(f"[BOT] Bot's hand: {' + '.join(bot_hand_display)}")
                elif action == 'pass':
                    bot_passed = True
                    # Show bot's hand with first card hidden as '?' and rest visible
                    bot_hand_display = ['?'] + bot_hand[1:]
                    print(f"[BOT] Passed!")
                    print(f"[BOT] Bot's hand: {' + '.join(bot_hand_display)}")
        
        # Evaluate exchange
        player_value = calc_hand_value(player_hand)
        bot_value = calc_hand_value(bot_hand)
        winner, _, _ = evaluate_exchange(player_hand, bot_hand, limit)
        
        print(f"\n" + "="*50)
        print(f"You: {player_value} | Bot: {bot_value}")
        
        if winner == 'host':
            player_distance += current_bet
            bot_distance -= current_bet
            print(f"YOU WIN! +{current_bet}")
        elif winner == 'player':
            bot_distance += current_bet
            player_distance -= current_bet
            print(f"BOT WINS! -{current_bet}")
        else:
            print(f"TIE!")
        
        print(f"Distance: You {player_distance} | Bot {bot_distance}")
        print("="*50)
        
        if player_distance <= 0:
            print("\n[GAME OVER] BOT WINS! You lost all distance!")
            break
        elif bot_distance <= 0:
            print("\n[GAME OVER] YOU WIN! Bot lost all distance!")
            break
        
        # Reset for next exchange
        player_hand = [deck.pop()] if deck else ['1']
        bot_hand = [deck.pop()] if deck else ['1']
        player_passed = False
        bot_passed = False

async def run_client():
    client = GameClient()
    if await client.connect():
        await client.main_menu()

async def main_menu():
    """Display main menu and route to game mode"""
    while True:
        print("\n" + "="*50)
        print("                 WELCOME TO 21              ")
        print("="*50)
        print("\n1. Play with BOT")
        print("2. Play ONLINE (Host or Join)")
        print("3. Exit")
        print("\n" + "="*50)
        
        choice = input("Choose option (1-3): ").strip()
        
        if choice == '1':
            await play_bot_mode()
        elif choice == '2':
            # Multiplayer mode
            print("\n" + "="*40)
            print("   ONLINE GAME MODE")
            print("="*40)
            print("1. Start Server (host a game)")
            print("2. Connect to Server (join a game)")
            print("3. Back to main menu")
            print("="*40)
            
            net_choice = input("Choose option (1-3): ").strip()
            
            if net_choice == '1':
                print("\nStarting SERVER mode...")
                print("[INFO] Server is running on ws://localhost:8765")
                print("[INFO] Other players can join with the code displayed.")
                print("[INFO] Press Ctrl+C to stop server")
                try:
                    await run_server()
                except KeyboardInterrupt:
                    print("\n[INFO] Server stopped.")
            elif net_choice == '2':
                print("\nConnecting to server...")
                await run_client()
            elif net_choice == '3':
                continue
            else:
                print("[ERROR] Invalid option!")
        elif choice == '3':
            print("\n[INFO] Thanks for playing!")
            break
        else:
            print("[ERROR] Invalid option!")

# ============ MAIN ============

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Command line mode (for running server/client directly)
        mode = sys.argv[1].lower()
        if mode == 'server':
            print("\nStarting SERVER mode...")
            asyncio.run(run_server())
        elif mode == 'client':
            print("\nStarting CLIENT mode...")
            asyncio.run(run_client())
        else:
            print(f"Unknown mode: {mode}")
    else:
        # Interactive menu mode
        asyncio.run(main_menu())

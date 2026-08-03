import sys
import math
import random
import pygame
import numpy as np
from pydartsnut import Dartsnut

def map_range(val, in_min, in_max, out_min, out_max):
    if in_max == in_min:
        return out_min
    return out_min + (val - in_min) * (out_max - out_min) / (in_max - in_min)

# Game States
STATE_TITLE = 0
STATE_AIM_POS = 1
STATE_AIM_ANGLE = 2
STATE_ROLLING = 3
STATE_RESULT = 4
STATE_GAME_OVER = 5

def main():
    pygame.init()
    pygame.font.init()
    
    # 128x160 logical display size
    screen = pygame.Surface((128, 160))
    display_screen = pygame.display.set_mode((128, 160))
    pygame.display.set_caption("Neon Bowling")
    
    clock = pygame.time.Clock()
    engine = Dartsnut()
    
    # Fonts
    font_small = pygame.font.Font(None, 14)
    font_medium = pygame.font.Font(None, 16)
    font_large = pygame.font.Font(None, 22)
    
    # Colors
    C_BG = (15, 15, 20)
    C_LANE = (235, 195, 140)
    C_GUTTER = (50, 45, 55)
    C_PIN_WHITE = (255, 255, 255)
    C_PIN_STRIPE = (255, 40, 40)
    C_BALL = (0, 255, 255)
    C_BALL_SHINE = (200, 255, 255)
    C_NEON_GREEN = (50, 255, 50)
    C_NEON_PINK = (255, 50, 150)
    C_NEON_YELLOW = (255, 216, 0)
    C_TEXT = (240, 240, 255)
    
    # Pin coordinates relative to lane deck
    # Center is X=64. Y coordinates from 36 to 48.
    PIN_POSITIONS = [
        (64, 48),  # Pin 1 (front)
        (60, 44), (68, 44),  # Pins 2, 3
        (56, 40), (64, 40), (72, 40),  # Pins 4, 5, 6
        (52, 36), (60, 36), (68, 36), (76, 36)  # Pins 7, 8, 9, 10
    ]
    
    # Pin knockdown cascade rules: mapping pin index to left and right pins behind it
    CASCADE_TARGETS = {
        0: {"left": 1, "right": 2},
        1: {"left": 3, "right": 4},
        2: {"left": 4, "right": 5},
        3: {"left": 6, "right": 7},
        4: {"left": 7, "right": 8},
        5: {"left": 8, "right": 9}
    }
    
    # Game variables
    state = STATE_TITLE
    current_frame = 1  # 1 to 10
    pins_standing = [True] * 10
    frame_rolls = []  # Rolls in the current frame
    all_rolls = []  # List of lists, tracking rolls for each completed frame
    
    # Ball state
    ball_x = 64.0
    ball_y = 120.0
    ball_vx = 0.0
    ball_vy = 0.0
    ball_spin = 0.0  # Player steering force
    ball_active = False
    in_gutter = False
    
    # Aiming state
    aim_pos_x = 64.0
    aim_angle = 0.0  # degrees (-15 to 15)
    aim_angle_dir = 1  # 1 or -1 for sweeping
    
    # Particles & screen shake
    particles = []
    shake_intensity = 0
    
    # Message display
    result_message = ""
    result_timer = 0
    result_sub_message = ""
    
    def spawn_pin_particles(x, y):
        for _ in range(8):
            particles.append({
                "x": x,
                "y": y,
                "vx": random.uniform(-2, 2),
                "vy": random.uniform(-3, 1),
                "color": random.choice([C_PIN_WHITE, C_NEON_YELLOW, C_NEON_PINK]),
                "life": random.randint(15, 30)
            })
            
    def trigger_cascade(hit_index, vx):
        queue = [hit_index]
        visited = {hit_index}
        
        while queue:
            curr = queue.pop(0)
            if curr in CASCADE_TARGETS:
                left = CASCADE_TARGETS[curr]["left"]
                right = CASCADE_TARGETS[curr]["right"]
                
                # Base knock down chance
                prob_left = 0.75 - vx * 0.3
                prob_right = 0.75 + vx * 0.3
                
                # Clamp probabilities
                prob_left = max(0.2, min(0.95, prob_left))
                prob_right = max(0.2, min(0.95, prob_right))
                
                if pins_standing[left] and left not in visited:
                    if random.random() < prob_left:
                        pins_standing[left] = False
                        spawn_pin_particles(PIN_POSITIONS[left][0], PIN_POSITIONS[left][1])
                        visited.add(left)
                        queue.append(left)
                        
                if pins_standing[right] and right not in visited:
                    if random.random() < prob_right:
                        pins_standing[right] = False
                        spawn_pin_particles(PIN_POSITIONS[right][0], PIN_POSITIONS[right][1])
                        visited.add(right)
                        queue.append(right)

    def calculate_score(frames_rolls):
        total = 0
        frame_scores = []
        flat_rolls = []
        frame_start_idx = []
        
        for f in frames_rolls:
            frame_start_idx.append(len(flat_rolls))
            flat_rolls.extend(f)
            
        for i in range(min(10, len(frames_rolls))):
            f = frames_rolls[i]
            if len(f) == 0:
                break
                
            start_idx = frame_start_idx[i]
            
            if i < 9:
                if f[0] == 10:  # Strike
                    if start_idx + 2 < len(flat_rolls):
                        frame_score = 10 + flat_rolls[start_idx + 1] + flat_rolls[start_idx + 2]
                        total += frame_score
                        frame_scores.append(total)
                    else:
                        frame_scores.append(None)
                elif sum(f) == 10:  # Spare
                    if start_idx + 2 < len(flat_rolls):
                        frame_score = 10 + flat_rolls[start_idx + 2]
                        total += frame_score
                        frame_scores.append(total)
                    else:
                        frame_scores.append(None)
                else:  # Open
                    frame_score = sum(f)
                    total += frame_score
                    frame_scores.append(total)
            else:  # Frame 10
                frame_score = sum(f)
                total += frame_score
                frame_scores.append(total)
                
        return total, frame_scores

    def get_current_display_score():
        total, _ = calculate_score(all_rolls + [frame_rolls] if frame_rolls else all_rolls)
        return total

    running = True
    while running and engine.running:
        # Check standard quit events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                
        # Get machine inputs
        button_events = engine.get_button_events()
        dart_hits = engine.get_dart_hits()
        
        # Determine if A was pressed or a dart was thrown
        a_pressed = button_events.get("btn_a")
        b_pressed = button_events.get("btn_b")
        up_pressed = button_events.get("btn_up")
        down_pressed = button_events.get("btn_down")
        left_pressed = button_events.get("btn_left")
        right_pressed = button_events.get("btn_right")
        
        # Handle dart hit action: start game or trigger roll directly
        dart_action = len(dart_hits) > 0
        hit_x = 64
        hit_y = 120
        if dart_action:
            # Map dart hit to lane coordinate space
            hit_index, dx, dy = dart_hits[0]
            hit_x = int(dx)
            hit_y = int(dy)
            
        # Update particles
        for p in particles[:]:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["life"] -= 1
            if p["life"] <= 0:
                particles.remove(p)
                
        # Screen shake dampening
        if shake_intensity > 0:
            shake_intensity -= 1
            
        # --- STATE MACHINE ---
        if state == STATE_TITLE:
            if a_pressed or dart_action:
                state = STATE_AIM_POS
                current_frame = 1
                pins_standing = [True] * 10
                frame_rolls = []
                all_rolls = []
                aim_pos_x = 64.0
                aim_angle = 0.0
                
        elif state == STATE_AIM_POS:
            # Move position with arrows
            if left_pressed:
                aim_pos_x = max(25.0, aim_pos_x - 3.0)
            if right_pressed:
                aim_pos_x = min(103.0, aim_pos_x + 3.0)
                
            # Lock position on A
            if a_pressed:
                state = STATE_AIM_ANGLE
                aim_angle = 0.0
                aim_angle_dir = 1
            elif dart_action:
                # Direct roll from dart hit coordinates
                ball_x = float(max(25.0, min(103.0, hit_x)))
                # Angle derived from distance to center
                angle_deg = (ball_x - 64.0) * 0.4
                ball_vx = math.sin(math.radians(angle_deg)) * 3.5
                ball_vy = -3.5
                ball_y = 120.0
                ball_spin = 0.0
                in_gutter = False
                state = STATE_ROLLING
                
        elif state == STATE_AIM_ANGLE:
            # Sweep angle
            aim_angle += aim_angle_dir * 1.5
            if aim_angle > 18.0:
                aim_angle = 18.0
                aim_angle_dir = -1
            elif aim_angle < -18.0:
                aim_angle = -18.0
                aim_angle_dir = 1
                
            # Lock angle and roll
            if a_pressed:
                ball_x = aim_pos_x
                ball_y = 120.0
                ball_vx = math.sin(math.radians(aim_angle)) * 3.5
                ball_vy = -3.5
                ball_spin = 0.0
                in_gutter = False
                state = STATE_ROLLING
            elif dart_action:
                # Direct roll from dart hit coordinates
                ball_x = float(max(25.0, min(103.0, hit_x)))
                angle_deg = (ball_x - 64.0) * 0.4
                ball_vx = math.sin(math.radians(angle_deg)) * 3.5
                ball_vy = -3.5
                ball_y = 120.0
                ball_spin = 0.0
                in_gutter = False
                state = STATE_ROLLING
                
        elif state == STATE_ROLLING:
            # Steer ball with left/right buttons
            if left_pressed:
                ball_vx -= 0.15
            if right_pressed:
                ball_vx += 0.15
                
            # Physics updates
            if not in_gutter:
                # Apply gradual spin/drift
                ball_x += ball_vx
                ball_y += ball_vy
                
                # Check gutter
                # Lane boundaries scale based on depth Y
                # Top lane center Y=35 width 24. Bottom lane center Y=128 width 98.
                lane_w = map_range(ball_y, 128.0, 35.0, 98.0, 24.0)
                left_bound = 64.0 - lane_w / 2.0
                right_bound = 64.0 + lane_w / 2.0
                
                if ball_x < left_bound:
                    in_gutter = True
                    ball_x = left_bound
                    ball_vx = 0.0
                elif ball_x > right_bound:
                    in_gutter = True
                    ball_x = right_bound
                    ball_vx = 0.0
            else:
                # Ball is in gutter, slide straight up
                ball_y += ball_vy
                # Keep aligned with the curved gutter line
                lane_w = map_range(ball_y, 128.0, 35.0, 98.0, 24.0)
                if ball_x < 64.0:
                    ball_x = 64.0 - lane_w / 2.0
                else:
                    ball_x = 64.0 + lane_w / 2.0
                    
            # Collision check with pins
            # Only hit pins if not in gutter
            if not in_gutter and ball_y <= 52.0:
                ball_r = int(map_range(ball_y, 120.0, 35.0, 6.0, 2.0))
                hit_any = False
                for idx, (px, py) in enumerate(PIN_POSITIONS):
                    if pins_standing[idx]:
                        # Distance check
                        dist = math.hypot(ball_x - px, ball_y - py)
                        if dist < (ball_r + 3.0):
                            pins_standing[idx] = False
                            spawn_pin_particles(px, py)
                            trigger_cascade(idx, ball_vx)
                            hit_any = True
                            
                if hit_any:
                    shake_intensity = 6
                    
            # Check if ball has exited the top of the lane
            if ball_y < 30.0:
                # Count standing pins before and after
                # Let's transition to Result state
                standing_before = 10 - sum(frame_rolls) if len(frame_rolls) == 1 else 10
                if current_frame == 10:
                    # In frame 10, pin resets can happen between rolls
                    # Let's simplify: check active pins before this roll
                    standing_before = sum(1 for p in pins_standing) + (10 - sum(1 for p in pins_standing) if all(not p for p in pins_standing) else 0)
                    # We will calculate exact pins knocked down based on current state
                
                # Count knocked down in this roll
                knocked_this_roll = 0
                # In standard logic, it's just the pins that went from True to False
                # Let's count standing pins now
                standing_now = sum(1 for p in pins_standing if p)
                
                # If frame 10 reset happened, or first roll
                if len(frame_rolls) == 0:
                    knocked_this_roll = 10 - standing_now
                elif len(frame_rolls) == 1:
                    # For roll 2
                    # If roll 1 was a strike, pins were reset, so we check against 10
                    if frame_rolls[0] == 10:
                        knocked_this_roll = 10 - standing_now
                    else:
                        knocked_this_roll = (10 - frame_rolls[0]) - standing_now
                elif len(frame_rolls) == 2:
                    # For roll 3 in frame 10
                    if sum(frame_rolls) in (10, 20):  # Reset occurred
                        knocked_this_roll = 10 - standing_now
                    else:
                        knocked_this_roll = (10 - sum(frame_rolls) % 10) - standing_now
                        
                frame_rolls.append(knocked_this_roll)
                
                # Determine feedback message
                if knocked_this_roll == 10 and len(frame_rolls) == 1:
                    result_message = "STRIKE!"
                    result_sub_message = "EXCELLENT!"
                elif len(frame_rolls) == 2 and sum(frame_rolls) == 10:
                    result_message = "SPARE!"
                    result_sub_message = "GREAT RECOVERY!"
                elif in_gutter:
                    result_message = "GUTTER BALL"
                    result_sub_message = "0 PINS"
                else:
                    result_message = f"{knocked_this_roll} PINS"
                    result_sub_message = "NICE TRY"
                    
                state = STATE_RESULT
                result_timer = 50  # frames to display (~1.6 seconds)
                
        elif state == STATE_RESULT:
            if result_timer > 0:
                result_timer -= 1
                if a_pressed or dart_action:
                    result_timer = 0
            else:
                # Frame routing logic
                if current_frame < 10:
                    # If strike or 2 rolls complete
                    if frame_rolls[0] == 10 or len(frame_rolls) == 2:
                        all_rolls.append(frame_rolls)
                        frame_rolls = []
                        pins_standing = [True] * 10
                        current_frame += 1
                        state = STATE_AIM_POS
                        aim_pos_x = 64.0
                    else:
                        # Second roll in progress
                        state = STATE_AIM_POS
                        aim_pos_x = 64.0
                else:
                    # Frame 10 logic
                    # Maximum 3 rolls
                    # If 3 rolls done, or 2 rolls done and sum < 10
                    done_10th = False
                    if len(frame_rolls) == 3:
                        done_10th = True
                    elif len(frame_rolls) == 2:
                        # If no strike on roll 1 and no spare on roll 2
                        if frame_rolls[0] != 10 and sum(frame_rolls) < 10:
                            done_10th = True
                            
                    if done_10th:
                        all_rolls.append(frame_rolls)
                        state = STATE_GAME_OVER
                    else:
                        # Reset pins if strike or spare
                        if frame_rolls[-1] == 10 or (len(frame_rolls) == 2 and sum(frame_rolls) == 10):
                            pins_standing = [True] * 10
                        state = STATE_AIM_POS
                        aim_pos_x = 64.0
                        
        elif state == STATE_GAME_OVER:
            if a_pressed or dart_action:
                state = STATE_TITLE
                
        # --- DRAWING ---
        # Apply screen shake offsets
        offset_x = random.randint(-shake_intensity, shake_intensity) if shake_intensity > 0 else 0
        offset_y = random.randint(-shake_intensity, shake_intensity) if shake_intensity > 0 else 0
        
        screen.fill(C_BG)
        
        # Draw top bar (Score & Frame)
        pygame.draw.rect(screen, (10, 10, 15), (0, 0, 128, 18))
        pygame.draw.line(screen, C_NEON_PINK, (0, 18), (128, 18), 1)
        
        txt_frame = font_small.render(f"FRAME: {min(10, current_frame)}/10", False, C_TEXT)
        screen.blit(txt_frame, (4, 4))
        
        total_scr = get_current_display_score()
        txt_score = font_small.render(f"SCORE: {total_scr}", False, C_NEON_GREEN)
        screen.blit(txt_score, (70, 4))
        
        # Draw Lane and surroundings
        # Background space outside lane
        lane_surf = pygame.Surface((128, 110))
        lane_surf.fill(C_GUTTER)
        
        # Lane shape
        # Top width 24 (center 64, bounds 52 to 76), Top Y=35 (shifted in local space to Y=17)
        # Bottom width 98 (bounds 15 to 113), Bottom Y=128 (local Y=110)
        lane_poly = [(15, 110), (113, 110), (76, 17), (52, 17)]
        pygame.draw.polygon(lane_surf, C_LANE, lane_poly)
        
        # Draw boards (wood lines)
        for i in range(1, 6):
            bx_bot = int(15 + i * (98 / 6.0))
            bx_top = int(52 + i * (24 / 6.0))
            pygame.draw.line(lane_surf, (180, 140, 90), (bx_bot, 110), (bx_top, 17), 1)
            
        # Draw arrows/markers on lane
        # Arrows at local Y=60 (approx. midway)
        for i in [-1.5, -0.5, 0.5, 1.5]:
            ax = int(64 + i * 12)
            ay = 70
            # Scale coords to perspective
            ax_p = int(map_range(ay, 110, 17, ax, 64 + (ax - 64) * 0.25))
            ay_p = ay
            pygame.draw.polygon(lane_surf, C_NEON_PINK, [
                (ax_p, ay_p), (ax_p - 2, ay_p + 4), (ax_p + 2, ay_p + 4)
            ])
            
        # Draw standing pins
        # Offset PIN_POSITIONS because they are in global coordinates (Y is 36 to 48)
        # Local Y = global Y - 18
        for idx, (px, py) in enumerate(PIN_POSITIONS):
            if pins_standing[idx]:
                local_py = py - 18
                # Draw white pin head/body
                pygame.draw.circle(lane_surf, C_PIN_WHITE, (px, local_py), 2)
                # Draw tiny red stripe
                pygame.draw.line(lane_surf, C_PIN_STRIPE, (px - 1, local_py), (px + 1, local_py), 1)
                
        # Draw ball if rolling or aiming
        if state in (STATE_ROLLING, STATE_AIM_POS, STATE_AIM_ANGLE):
            draw_bx = ball_x
            draw_by = ball_y - 18
            ball_r = int(map_range(ball_y, 120.0, 35.0, 6.0, 2.0))
            
            # Glow / shadow
            pygame.draw.circle(lane_surf, (0, 100, 100), (int(draw_bx), int(draw_by)), ball_r + 1, 1)
            # Main ball
            pygame.draw.circle(lane_surf, C_BALL, (int(draw_bx), int(draw_by)), ball_r)
            # Shine dot
            if ball_r >= 3:
                pygame.draw.circle(lane_surf, C_BALL_SHINE, (int(draw_bx - ball_r/3), int(draw_by - ball_r/3)), 1)
                
        # Draw aiming indicators
        if state == STATE_AIM_POS:
            # Draw blinking position arrows at the bottom of the lane
            arrow_y = 100
            if (pygame.time.get_ticks() // 200) % 2 == 0:
                pygame.draw.polygon(lane_surf, C_NEON_YELLOW, [(int(aim_pos_x) - 8, arrow_y), (int(aim_pos_x) - 4, arrow_y - 3), (int(aim_pos_x) - 4, arrow_y + 3)])
                pygame.draw.polygon(lane_surf, C_NEON_YELLOW, [(int(aim_pos_x) + 8, arrow_y), (int(aim_pos_x) + 4, arrow_y - 3), (int(aim_pos_x) + 4, arrow_y + 3)])
                
        elif state == STATE_AIM_ANGLE:
            # Draw vector aim line
            line_len = 30
            rad = math.radians(aim_angle - 90)
            end_x = aim_pos_x + math.cos(rad) * line_len
            end_y = 102 + math.sin(rad) * line_len
            pygame.draw.line(lane_surf, C_NEON_YELLOW, (int(aim_pos_x), 102), (int(end_x), int(end_y)), 1)
            
        # Draw particles
        for p in particles:
            pygame.draw.circle(lane_surf, p["color"], (int(p["x"]), int(p["y"] - 18)), 1)
            
        # Blit lane onto main screen with offset shake
        screen.blit(lane_surf, (offset_x, 18 + offset_y))
        
        # Draw bottom panel (HUD/Score/Controls)
        pygame.draw.rect(screen, (5, 5, 8), (0, 128, 128, 32))
        pygame.draw.line(screen, C_NEON_PINK, (0, 128), (128, 128), 1)
        
        if state == STATE_TITLE:
            # Title Screen overlay on lane/bottom
            pygame.draw.rect(screen, (10, 10, 15), (10, 45, 108, 70))
            pygame.draw.rect(screen, C_NEON_PINK, (10, 45, 108, 70), 1)
            
            title_t = font_large.render("NEON BOWL", False, C_NEON_GREEN)
            screen.blit(title_t, (22, 55))
            
            # Blinking press key
            if (pygame.time.get_ticks() // 500) % 2 == 0:
                start_t = font_small.render("PRESS A TO ROLL", False, C_NEON_YELLOW)
                screen.blit(start_t, (24, 85))
                
            ctrl_t = font_small.render("OR THROW A DART!", False, C_TEXT)
            screen.blit(ctrl_t, (22, 100))
            
            # Bottom panel instructions
            inst_t = font_small.render("DART / BUTTON PLAY", False, C_TEXT)
            screen.blit(inst_t, (14, 138))
            
        elif state == STATE_AIM_POS:
            inst_t = font_small.render("LEFT/RIGHT: POSITION", False, C_TEXT)
            screen.blit(inst_t, (10, 133))
            action_t = font_small.render("PRESS A: LOCK POSITION", False, C_NEON_YELLOW)
            screen.blit(action_t, (6, 147))
            
        elif state == STATE_AIM_ANGLE:
            inst_t = font_small.render("AUTO SWEEPER ACTIVE", False, C_TEXT)
            screen.blit(inst_t, (10, 133))
            action_t = font_small.render("PRESS A: RELEASE BALL", False, C_NEON_GREEN)
            screen.blit(action_t, (8, 147))
            
        elif state == STATE_ROLLING:
            inst_t = font_small.render("STEER MID-ROLL!", False, C_NEON_GREEN)
            screen.blit(inst_t, (22, 133))
            action_t = font_small.render("PRESS LEFT/RIGHT SPIN", False, C_TEXT)
            screen.blit(action_t, (8, 147))
            
        elif state == STATE_RESULT:
            # Show big result message
            msg_t = font_large.render(result_message, False, C_NEON_YELLOW)
            sub_t = font_small.render(result_sub_message, False, C_TEXT)
            
            # Center text
            msg_x = (128 - msg_t.get_width()) // 2
            sub_x = (128 - sub_t.get_width()) // 2
            
            screen.blit(msg_t, (msg_x, 132))
            screen.blit(sub_t, (sub_x, 148))
            
        elif state == STATE_GAME_OVER:
            # Show game over scoreboard
            pygame.draw.rect(screen, (10, 10, 15), (10, 30, 108, 90))
            pygame.draw.rect(screen, C_NEON_YELLOW, (10, 30, 108, 90), 1)
            
            go_t = font_large.render("GAME OVER", False, C_NEON_PINK)
            screen.blit(go_t, (22, 38))
            
            sc_t = font_medium.render(f"FINAL SCORE: {total_scr}", False, C_NEON_GREEN)
            screen.blit(sc_t, (20, 65))
            
            again_t = font_small.render("PRESS A TO RESET", False, C_TEXT)
            screen.blit(again_t, (22, 90))
            
            # Bottom panel
            inst_t = font_small.render("CONGRATULATIONS!", False, C_NEON_YELLOW)
            screen.blit(inst_t, (14, 138))
            
        # Draw everything to actual display
        display_screen.blit(screen, (0, 0))
        pygame.display.flip()
        
        # Push frame to Dartsnut hardware/emulator
        engine.update_frame_buffer(np.transpose(pygame.surfarray.array3d(screen), (1, 0, 2)))
        
        clock.tick(30)
        
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

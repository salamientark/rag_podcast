import { tool } from 'ai';
import { z } from 'zod';
import { sign } from 'jsonwebtoken';

const SolverURL = process.env.SOLVER_API_URL;
const SolverSecret = process.env.SOLVER_SECRET;

function issueJWT(secret: string): string {
  return sign(
    {
      /* optional custom claims */
    },
    secret,
    { algorithm: 'HS256', expiresIn: 30 /* seconds */ },
  );
}

const pokerSolverParams = z.object({
  number_of_players: z
    .number()
    .describe('Total number of players at the table.'),
  main_player_hand: z
    .string()
    .describe(
      "The hole cards of the main player, formatted as 'AhJc'. Transform the 'suited'/'offsuit' terminology into any matching suit",
    ),
  main_player_position: z
    .string()
    .describe('Position of the main player (SB/BB/UTG/HJ/CO/BTN).'),
  community_cards: z
    .string()
    .describe(
      "Optional community cards dealt on the table, formatted as 'AhJc'. Empty if preflop.",
    ),
  actions: z
    .object({
      preflop: z
        .array(
          z
            .object({
              action: z
                .string()
                .describe(
                  "Action taken by the player, can be 'c' for check or call; 'bX' for bet where X is the bet amount. A bet can also be 'X%' for percentage of pot where X is an integer (e.g. '50%' for half pot bet, not '50.5%').",
                ),
              playerPos: z
                .string()
                .describe(
                  'Position of the player taking the action (e.g., SB/BB/UTG/HJ/CO/BTN).',
                ),
            })
            .required(),
        )
        .describe('Array of preflop actions taken by players.'),
      flop: z
        .array(
          z
            .object({
              action: z
                .string()
                .describe(
                  "Action taken by the player, can be 'c' for check or call; 'bX' for bet where X is the bet amount. A bet can also be 'X%' for percentage of pot where X is an integer (e.g. '50%' for half pot bet, not '50.5%').",
                ),
              playerPos: z
                .string()
                .describe(
                  'Position of the player taking the action (e.g., SB/BB/UTG/HJ/CO/BTN).',
                ),
            })
            .required(),
        )
        .optional()
        .describe('Array of flop actions taken by players.'),
      turn: z
        .array(
          z
            .object({
              action: z
                .string()
                .describe(
                  "Action taken by the player, can be 'c' for check or call; 'bX' for bet where X is the bet amount. A bet can also be 'X%' for percentage of pot where X is an integer (e.g. '50%' for half pot bet, not '50.5%').",
                ),
              playerPos: z
                .string()
                .describe(
                  'Position of the player taking the action (e.g., SB/BB/UTG/HJ/CO/BTN).',
                ),
            })
            .required(),
        )
        .optional()
        .describe('Array of turn actions taken by players.'),
      river: z
        .array(
          z
            .object({
              action: z
                .string()
                .describe(
                  "Action taken by the player, can be 'c' for check or call; 'bX' for bet where X is the bet amount. A bet can also be 'X%' for percentage of pot where X is an integer (e.g. '50%' for half pot bet, not '50.5%').",
                ),
              playerPos: z
                .string()
                .describe(
                  'Position of the player taking the action (e.g., SB/BB/UTG/HJ/CO/BTN).',
                ),
            })
            .required(),
        )
        .optional()
        .describe('Array of river actions taken by players.'),
    })
    .describe('Actions taken by players, organized by street.'),
  // @TODO: STACK parameter
});

export const pokerSolver = tool({
  description:
    'Solve poker hands based on given game state. Assume deep cash game: Effective stack of at least 100BB for each player. Fold actions are inferred. No need to make them explicit, especially preflop.',
  parameters: pokerSolverParams,
  execute: async (params) => {
    if (!SolverURL || !SolverSecret) {
      console.log('Invalid solver configuration');
      return;
    }

    console.log('DEMANDING SOLVER');
    try {
      const response = await fetch(`${SolverURL}/api/v1/openai/poker-solver`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${issueJWT(SolverSecret)}`,
        },
        body: JSON.stringify(params),
      });

      if (!response.ok) {
        // Log the status code and response text
        console.log('ARG:', JSON.stringify(params));
        console.error(`HTTP Error: ${response.status}`);
        const errorText = await response.text();
        console.error(`Response: ${errorText}`);
        return errorText;
        // throw new Error(`HTTP error! status: ${response.status}`);
      }

      const result = await response.json();
      return result;
    } catch (error) {
      console.log('ARG:', JSON.stringify(params));
      console.error(error);
    }
  },
});

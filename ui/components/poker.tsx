import {
  Accordion, AccordionContent,
  AccordionItem, AccordionTrigger,
} from "@/components/ui/accordion"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export function PokerSolverUI({ result, args }: { result: any; args: any }) {
  if (typeof result === 'string' && result.toLowerCase().includes('error')) {
    console.log("Error while calling solver:\n", result)
    console.log("error args:\n", JSON.stringify({ args }))
    return null
  }

  console.log("SOLVER:\n", JSON.stringify({ args, result }, null, 2))

  // Check if result has policy data
  if (!result || !result.policy) return null;

  const policy = result.policy;

  // Transform action codes to readable names
  const transformAction = (action: string, hasFoldA: boolean): string => {
    if (action === 'f') return 'Fold';
    if (action === 'c') return hasFoldA ? 'Call' : 'Check';
    if (action.startsWith('b')) {
      const betSize = action.substring(1);
      return `Bet ${betSize}`;
    }
    return action;
  };

  // Parse percentage and filter out actions below 0.1%
  const parsePercentage = (percentStr: string): number => {
    return parseFloat(percentStr.replace('%', ''));
  };

  // Convert policy to array and filter
  const policyEntries = Object.entries(policy)
    .map(([action, percentage]) => ({
      action,
      percentage: percentage as string,
      numericPercentage: parsePercentage(percentage as string)
    }));
  const hasFoldA = policyEntries.map(e => e.action).includes('f');

  // Sort: fold first, then check/call, then bets by size
  const sortedEntries = policyEntries
    .filter(entry => entry.numericPercentage > 0.1)
    .sort((a, b) => {
      if (a.action === 'f') return -1;
      if (b.action === 'f') return 1;
      if (a.action === 'c') return -1;
      if (b.action === 'c') return 1;

      // Both are bets, sort by bet size
      if (a.action.startsWith('b') && b.action.startsWith('b')) {
        const aBetSize = parseFloat(a.action.substring(1));
        const bBetSize = parseFloat(b.action.substring(1));
        return aBetSize - bBetSize;
      }

      return 0;
    });

  return (
    <Accordion type="single" collapsible className="md:max-w-[250px]">
      <AccordionItem value="solver-results" className="border-none">
        <AccordionTrigger className="text-sm hover:no-underline py-2">
          Advanced Strategy Details
        </AccordionTrigger>
        <AccordionContent>
          <Table className="md:max-w-[250px] text-s">
            {/* <TableCaption>Poker Solver Policy</TableCaption> */}
            <TableHeader>
              <TableRow>
                <TableHead className="h-8 px-2 py-1">Action</TableHead>
                <TableHead className="text-right h-8 px-2 py-1">Probability</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedEntries.map((entry) => (
                <TableRow key={entry.action}>
                  <TableCell className="font-medium px-2 py-1">{transformAction(entry.action, hasFoldA)}</TableCell>
                  <TableCell className="text-right px-2 py-1">{entry.percentage}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

from __future__ import division

import decimal
import operator

from pyparsing import (
    Forward, Literal, Optional, StringEnd, Word, ZeroOrMore, alphanums, alphas,
    nums,
)

__all__ = ('Calculator', 'BonusPointCalculator')

Zero = decimal.Decimal(0)

# Atoms

Identifier = Word(alphas, alphanums + '_').setName('identifier')
Integer = (Optional('-') + Word(nums)).setParseAction(
    lambda s, loc, toks: ''.join(toks)).setName('integer')

# Literals

LeftParenthesis = Literal('(')
RightParenthesis = Literal(')')

LeftBracket = Literal('[')
RightBracket = Literal(']')

Colon = Literal(':')
Comma = Literal(',')

# Groups of Literals (all OR cases)
# Note: order matters, longer tokens must be listed first!
#   eg. '>=' before '>'

Addition = (Literal('+') | Literal('-')).setName('addop')
Multiplication = (Literal('*') | Literal('/')).setName('mulop')
Comparison = (
    Literal('=') | Literal('>=') | Literal('<=') | Literal('>') | Literal('<')
).setName('comparison')


class Calculator(object):

    def __init__(self, instance, *args, **kwargs):
        Expression = Forward()
        Atom = (
            (Identifier | Integer).setParseAction(self._push) |
            (LeftParenthesis + Expression.suppress() + RightParenthesis)
        ).setName('atom')
        Terminal = Atom + ZeroOrMore((Multiplication + Atom)
                                     .setParseAction(self._push))
        Expression << Terminal + ZeroOrMore((Addition + Terminal)
                                            .setParseAction(self._push))

        self.Operators = {
            "+": operator.add,
            "-": operator.sub,
            "*": operator.mul,
            "/": operator.truediv,
        }

        self.instance = instance
        self.pattern = Expression + StringEnd()
        self.stack = []

    def evaluate(self):
        try:
            token = self.stack.pop()
        except IndexError:
            return None
        if token in self.Operators:
            func = self.Operators.get(token)
            rhs = self.evaluate()
            lhs = self.evaluate()
            return func(lhs, rhs)
        elif Identifier.re.match(token):
            return getattr(self.instance, token, Zero)
        try:
            return decimal.Decimal(token)
        except decimal.InvalidOperation:
            return Zero

    def parse(self, data):
        self.pattern.parseString(data)

    def _push(self, string, position, tokens):
        """Add an element to the parse stack"""
        self.stack.append(tokens[0])


class BonusPointCalculator(Calculator):
    """
    Examples:

        Sydney Uni Touch
        "[win=1, score_against=0, forfeit_for=0: 1] + [loss=1, margin<=2: 1]"

        Super 14 Rugby
        "[tries>=4: 1] + [loss=1, margin<=7: 1]"
    """
    def __init__(self, *args, **kwargs):
        super(BonusPointCalculator, self).__init__(*args, **kwargs)

        self.Operators.update({
            "=": operator.eq,
            ">": operator.gt,
            "<": operator.lt,
            ">=": operator.ge,
            "<=": operator.le,
            ",": operator.and_,
            "[": lambda a, b: a and b or Zero,
            "]": lambda a, b: a and b or Zero,
        })

        BonusPointAddition = Addition | Comparison

        Expression = Forward()
        Atom = (
            (Identifier | Integer).setParseAction(self._push) |
            (LeftParenthesis + Expression.suppress() + RightParenthesis)
        )
        Terminal = Atom + ZeroOrMore((Multiplication + Atom)
                                     .setParseAction(self._push))
        Expression << Terminal + ZeroOrMore((BonusPointAddition + Terminal)
                                            .setParseAction(self._push))
        Condition = Expression + ZeroOrMore((Comma + Expression)
                                            .setParseAction(self._push))

        Rule = (LeftBracket +
                Condition +
                Colon +
                Expression +
                RightBracket).setParseAction(self._push)
        Chain = Rule + ZeroOrMore((Addition + Rule).setParseAction(self._push))

        self.pattern = Chain + StringEnd()

    def parse(self, data):
        if data.strip():
            self.pattern.parseString(data)

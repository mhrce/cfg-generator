from typing import List, Tuple, Any, Union
from antlr4 import RuleContext
from data_structures.graph.builder_interface import IDiGraphBuilder
from src.cfg_extractor.language_structure.structure_pattern_interface import ILanguagePattern
from src.data_structures.graph.builder_interface import IDiGraphBuilder
from src.data_structures.graph.networkx_builder import NxDiGraphBuilder as DiGraphBuilder
from enum import Enum, auto
from src.antlr.rule_utils import is_break, is_return, is_continue, is_throw, extract_exact_text
from src.antlr.gen.JavaParser import JavaParser
from antlr4.xpath.XPath import XPath
from functools import reduce
import operator


class EdgeLabel(Enum):
    false = auto()
    true = auto()


class DiGraphEmbedder(ILanguagePattern):

    @classmethod
    def concat(cls, left: IDiGraphBuilder, right: IDiGraphBuilder) -> IDiGraphBuilder:
        right = right >> len(left)

        g = (DiGraphBuilder()
             .add_nodes_from([(left.last, []), (right.head, [])])
             .add_edge(left.last, right.head))
        return g | left | right

    @classmethod
    def merge(cls, left: IDiGraphBuilder, right: IDiGraphBuilder) -> IDiGraphBuilder:
        if right is not None:
            right = right >> len(left) - 1
            return left | right
        else:
            return left

    @classmethod
    def embed_in_if(cls, condition: RuleContext, then_part: "IDiGraphBuilder"):
        g_head = 0
        g = DiGraphBuilder().add_node(g_head, value=[condition])
        then_part = then_part >> len(g)
        g_last = then_part.last + 1
        g.add_node(g_last, value=[])
        g = g | then_part
        return g.add_edges_from([(g_head, g_last, EdgeLabel.false.name),
                                 (g_head, then_part.head, EdgeLabel.true.name),
                                 (then_part.last, g_last)])

    @classmethod
    def embed_in_if_else(cls, condition: RuleContext, then_part: "IDiGraphBuilder", else_part: "IDiGraphBuilder"):
        g_head = 0
        g = DiGraphBuilder().add_node(g_head, value=[condition])
        then_part = then_part >> len(g)
        else_part = else_part >> len(g) + len(then_part)
        g = g | then_part | else_part
        g_last = g.last + 1
        g.add_node(g_last, value=[])
        return g.add_edges_from([(g_head, else_part.head, EdgeLabel.false.name),
                                 (g_head, then_part.head, EdgeLabel.true.name),
                                 (then_part.last, g_last),
                                 (else_part.last, g_last)])

    @classmethod
    def embed_in_switch_case(cls, switcher: RuleContext, labels: List[RuleContext], bodies: List["IDiGraphBuilder"]):
        g_head = 0
        start = 1
        shifted_bodies = []
        g = DiGraphBuilder().add_node(g_head, value=[switcher] if switcher else [])
        for i in range(len(bodies)):
            shifted_bodies.append(bodies[i] >> start)
            start = shifted_bodies[i].last + 1
        g_last = shifted_bodies[-1].last + 1
        for bodies_object in shifted_bodies:
            g = g | bodies_object
        g.add_node(g_last, value=[])
        g.add_edges_from(
            [(g_head, body.head, label.getText() if label else "") for label, body in
             zip(reduce(operator.concat, list(labels)), shifted_bodies)])
        g.add_edges_from([(body.last, body.last + 1) for label, body in zip(labels, shifted_bodies)])
        return cls.__split_on_break(g, g.last)

    @classmethod
    def embed_in_while(cls, condition: RuleContext, body: "IDiGraphBuilder"):
        g_head, g_condition = 0, 1
        g = DiGraphBuilder().add_nodes_from([(g_head, []),
                                             (g_condition, [condition])])
        body = body >> len(g)
        g_last = body.last + 1
        g.add_node(g_last, value=[])
        g = g | body
        g.add_edges_from([(g_head, g_condition),
                          (g_condition, body.head, EdgeLabel.true.name),
                          (g_condition, g_last, EdgeLabel.false.name),
                          (body.last, g_condition)])
        g = cls.__split_on_continue(g, g_condition)
        return cls.__split_on_break(g, g.last)

    @classmethod
    def embed_in_do_while(cls, condition: RuleContext, body: "IDiGraphBuilder"):
        g_head = 0
        g = DiGraphBuilder().add_node(g_head, [])
        body = body >> len(g)
        g_condition = body.last + 1
        g_last = g_condition + 1
        g.add_nodes_from([(g_condition, [condition]),
                          (g_last, [])])
        g = g | body
        g.add_edges_from([(g_head, body.head),
                          (body.last, g_condition),
                          (g_condition, body.head, EdgeLabel.true.name),
                          (g_condition, g_last, EdgeLabel.false.name)])
        g = cls.__split_on_continue(g, g_condition)
        return cls.__split_on_break(g, g.last)

    @classmethod
    def embed_in_for(cls,
                     condition,
                     initializer: RuleContext,
                     successor: IDiGraphBuilder,
                     body: RuleContext) -> IDiGraphBuilder:
        g, ref = (cls.__embed_in_conditional_for(condition, initializer, successor, body) if condition
             else cls.__embed_in_unconditional_for(initializer, successor, body))
        return cls.__split_on_break(g, ref)

    @classmethod
    def __embed_in_conditional_for(cls,
                                   condition: RuleContext,
                                   initializer: RuleContext,
                                   successor: RuleContext,
                                   body: IDiGraphBuilder) -> tuple[
        Union[tuple[IDiGraphBuilder, list[tuple[Any, Any]]], IDiGraphBuilder], int]:

        g_head, g_condition = 0, 1
        g = DiGraphBuilder().add_nodes_from([(g_head, [initializer]) if initializer else (g_head, []),
                                             (g_condition, [condition])])
        body = body >> len(g)
        g_successor = body.last + 1
        g_last = g_successor + 1
        g.add_nodes_from([(g_last, []), (g_successor, [successor] if successor else [])])
        g = g | body
        g.add_edges_from([(g_head, g_condition), (g_condition, body.head, EdgeLabel.true.name),
                          (g_condition, g_last, EdgeLabel.false.name), (body.last, g_successor),
                          (g_successor, g_condition)])
        return cls.__split_on_continue(g, g_successor), g_last

    @classmethod
    def __embed_in_unconditional_for(cls,
                                     initializer: RuleContext,
                                     successor: RuleContext,
                                     body: IDiGraphBuilder) -> tuple[
        Union[tuple[IDiGraphBuilder, list[tuple[Any, Any]]], IDiGraphBuilder], int]:
        g_head = 0
        g = DiGraphBuilder().add_node(g_head, [initializer] if initializer else [])
        body = body >> len(g)
        g_successor = body.last + 1
        g_last = g_successor + 1
        g.add_nodes_from([(g_last, []), (g_successor, [successor] if successor else [])])
        g = g | body
        g.add_edges_from([(g_head, body.head),
                          (body.last, g_successor),
                          (g_successor, body.head)])
        return cls.__split_on_continue(g, g_successor), g_last

    @classmethod
    def embed_in_try_catch(cls,
                           try_body: "IDiGraphBuilder",
                           exceptions: List[RuleContext],
                           catch_bodies: List["IDiGraphBuilder"]):
        catches = []
        g = DiGraphBuilder()
        g = g | try_body
        for catch, exception in zip(catch_bodies, exceptions):
            catches.extend([(catch, exception)])
        return cls.__split_on_throw(g, catches)

    @classmethod
    def __resolve_null_node(cls, graph: IDiGraphBuilder, catches, lastNodes):
        # this is a list to store end nodes for graphviz
        newLastNodes = lastNodes

        # remove null nodes
        h = graph.copy()
        for node, data in graph.node_items:
            if not data:
                # get previous, next, and edges for null node
                predecessors = list(h.predecessors(node))
                successors = list(h.successors(node))
                edges = sorted(h.edge_items)
                if successors:
                    for pred in predecessors:
                        for s in successors:
                            # connect previous node to next node
                            h.add_edges_from([(pred, s, edge_label) for edge_nodes, edge_label in edges if edge_nodes == (pred, node)])
                            if (node, s) in edges:
                                h.remove_edge(node, s)

                        h.remove_edge(pred, node)
                else:
                    # if node doesn't have next node, recognize it as end node
                    for pred in predecessors:
                        newLastNodes.extend([(pred, [h[pred], edge_label]) for edge_nodes, edge_label in edges if edge_nodes == (pred, node)])
                        h.remove_edge(pred, node)

                h.remove_node(node)

        h.reset_node_order()
        newLastNodes = h.reset_list_order(newLastNodes)
        h_length = len(h)
        for catch in catches:
            tmp = catch[0] >> h_length
            h = h | tmp
            h_length += len(tmp)
            h = cls.__resolve_catch_null_nodes(h)

        return h, newLastNodes

    @classmethod
    def __resolve_catch_null_nodes(cls, graph: IDiGraphBuilder):
        h = graph.copy()
        for node, data in graph.node_items:
            if not data:
                # get previous, next, and edges for null node
                sucss = list(graph.successors(node))
                edges = sorted([edge for edge in graph.edge_items if node in edge[0]], key=lambda d: d[0][0])
                for edge in edges:
                    if edge[0][1] == node:
                        if sucss:
                            # connect previous node to next node
                            h.add_edges_from([(edge[0][0], s, edge[1].getText()) for s in sucss])
                            h.remove_edge(edge[0][0], node)
                            h.remove_edges_from([(node, s) for s in sucss])

                        else:
                            # if node doesn't have next node, recognize it as end node
                            h.remove_edge(edge[0][0], node)

                h.remove_node(node)

        h.reset_node_order()
        return h

    @classmethod
    def embed_in_function(cls, body: "IDiGraphBuilder", catches):
        g = DiGraphBuilder()
        g = g | body if body is not None else g.add_node(0, [])
        g, catches = cls.__split_on_throw(g, [])
        g, lastNodes = cls.__split_on_return(g)
        return cls.__resolve_null_node(g, catches, lastNodes)

    @classmethod
    def __split_on_return(cls, graph: IDiGraphBuilder):
        return cls.__direct_nodes_to_if(graph, None, is_return)

    @classmethod
    def __split_on_continue(cls, graph: "IDiGraphBuilder", direction_reference):
        return cls.__direct_nodes_to_if(graph, direction_reference, is_continue)

    @classmethod
    def __split_on_break(cls, graph: "IDiGraphBuilder", direction_reference):
        return cls.__direct_nodes_to_if(graph, direction_reference, is_break)

    @classmethod
    def __split_on_throw(cls, graph: "IDiGraphBuilder", catches):
        free_catches = []
        throwFlag = False
        h = graph.copy()
        for label, data in graph.node_items:
            for ctx in data:
                if is_throw(ctx):
                    throwFlag = True
                    catch_matched = False
                    h.remove_nodes_from(graph.descendants(label))
                    if catches:
                        for catch in catches:
                            if XPath.findAll(catch[1], "//catchType", JavaParser)[0].getText() == \
                                    XPath.findAll(ctx, "//classOrInterfaceTypeToInstantiate", JavaParser)[0].getText():
                                tmp = catch[0] >> len(h)
                                h = h | tmp
                                h.add_edge(label, tmp.head, catch[1].getText())
                                catch_matched = True
                            else:
                                free_catches.extend([(catch[0], None)])

                        if not catch_matched:
                            h_last_node = len(h)
                            h.add_node(h_last_node, [])
                            h.add_edge(label, h_last_node,
                                       XPath.findAll(ctx, "//classOrInterfaceTypeToInstantiate", JavaParser)[
                                           0].getText())


                    else:
                        h_last_node = len(h)
                        h.add_node(h_last_node, [])
                        h.add_edge(label, h_last_node,
                                   XPath.findAll(ctx, "//classOrInterfaceTypeToInstantiate", JavaParser)[0].getText())

                    h[label] = data[:data.index(ctx) + 1]

        if not throwFlag and catches:
            free_catches.extend(catches)

        h.reset_node_order()
        return h, free_catches

    @classmethod
    def __direct_nodes_to_if(cls,
                             graph: "IDiGraphBuilder",
                             target_node,
                             jump_statement):
        lastNodes = []
        h = graph.copy()
        for label, data in graph.node_items:
            for ctx in data:
                if ctx:
                    if jump_statement(ctx):
                        if list(graph.successors(label)):
                            h.remove_edges_from([(label, successor) for successor in graph.successors(label)])
                            if target_node is None:
                                lastNodes.extend([(label, [data, None])])
                            else:
                                h.add_edge(label, target_node)
                                h[label] = data[:data.index(ctx)]

                        else:
                            if target_node is None:
                                lastNodes.extend([(label, [data, None])])
                                h[label] = data[:data.index(ctx) + 1]

        h.reset_node_order()
        if target_node is None:
            return h, lastNodes
        else:
            return h

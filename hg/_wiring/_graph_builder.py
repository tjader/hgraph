import typing
from collections import defaultdict

if typing.TYPE_CHECKING:
    from hg._builder._graph_builder import GraphBuilder, GraphBuilderFactory

__all__ = ("wire_graph",)


def wire_graph(graph, *args, **kwargs) -> "GraphBuilder":
    """
    Evaluate the wiring graph and build a runtime graph.
    This graph is the actual graph objects that are used to be evaluated.
    """
    from hg import WiringGraphContext
    from hg._wiring._wiring import WiringNodeInstance
    from hg._builder._graph_builder import Edge
    from hg._builder._node_builder import NodeBuilder
    from hg._runtime._node import NodeTypeEnum

    from hg._builder._ts_builder import TimeSeriesBuilderFactory
    from hg._builder._graph_builder import GraphBuilder, GraphBuilderFactory
    from hg._wiring._wiring_errors import WiringError

    if not TimeSeriesBuilderFactory.has_instance():
        TimeSeriesBuilderFactory.declare_default_factory()

    try:
        with WiringGraphContext(None) as context:
            out = graph(*args, **kwargs)
            # For now let's ensure that top level graphs do not return anything.
            # Later we can consider default behaviour for graphs with outputs.
            assert out is None, "Currently only graph with no return values are supported"

            # Build graph by walking from sink nodes to parent nodes.
            # Also eliminate duplicate nodes
            sink_nodes = context.sink_nodes
            max_rank = max(node.rank for node in sink_nodes)
            ranked_nodes: dict[int, set[WiringNodeInstance]] = defaultdict(set)

            pending_nodes = list(sink_nodes)
            while pending_nodes:
                node = pending_nodes.pop()
                if (rank := node.rank) == 1:
                    # Put all push nodes at rank 0 and pull nodes at rank 1
                    rank = 0 if node.resolved_signature.node_type is NodeTypeEnum.PUSH_SOURCE_NODE else 1
                if node.resolved_signature.node_type is NodeTypeEnum.SINK_NODE:
                    # Put all sink nodes at max_rank
                    rank = max_rank
                ranked_nodes[node.rank].add(node)
                for arg in node.resolved_signature.time_series_args:
                    pending_nodes.append(node.inputs[arg].node_instance)

            # Now we can walk the tree in rank order and construct the nodes
            node_map: dict[WiringNodeInstance, int] = {}
            node_builders: [NodeBuilder] = []
            edges: set[Edge] = set[Edge]()
            for i in range(max_rank + 1):
                wiring_node_set = ranked_nodes.get(i, set())
                for wiring_node in wiring_node_set:
                    ndx = len(node_builders)
                    node_builder, input_edges = wiring_node.create_node_builder_and_edges(node_map, node_builders)
                    node_builders.append(node_builder)
                    edges.update(input_edges)
                    node_map[wiring_node] = ndx

        return GraphBuilderFactory.make(node_builders=tuple[NodeBuilder, ...](node_builders),
                                        edges=tuple[Edge, ...](
                                            sorted(edges,
                                                   key=lambda e: (
                                                       e.src_node, e.dst_node, e.output_path, e.input_path))))
    except WiringError as e:
        e.print_error()
        raise e

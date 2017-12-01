from test_plus import TestCase
from touchtechnology.common.tests import factories


class SitemapMoveTest(TestCase):

    def test_move_down_up(self):
        user = factories.UserFactory.create(is_staff=True, is_superuser=True)
        root = factories.SitemapNodeFactory.create()
        factories.SitemapNodeFactory.create_batch(parent=root, size=4)

        # baseline for the mptt values of the nodes, order by pk to ensure
        # subsequent check is valid
        before_move = sorted(
            root.get_children().values_list('pk', 'lft', 'rght', 'tree_id'))

        # perform the move using the admin view
        with self.login(user):
            self.get('admin:reorder', before_move[0][0], 'down')
            self.response_302()

            # after moving the node down make sure the mptt values are different
            after_move_1 = sorted(
                root.get_children().values_list('pk', 'lft', 'rght', 'tree_id'))
            self.assertNotEqual(before_move, after_move_1)

            # try moving the node back up
            self.get('admin:reorder', before_move[0][0], 'up')
            self.response_302()

            # after moving the node up the mptt values should be restored
            after_move_2 = sorted(
                root.get_children().values_list('pk', 'lft', 'rght', 'tree_id'))
            # self.assertNotEqual(after_move_1, after_move_2)
            self.assertEqual(before_move, after_move_2)
